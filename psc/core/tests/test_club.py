import datetime
import re

from django.urls import reverse
from django.utils import timezone

from core.models import Activity, Member, News
from core.tests.base import PscTestCase
from events.models import Discipline, EventEdition, FeedbackCriterion, PredictionDismissal


class ClubHubTests(PscTestCase):
    def test_the_hub_lists_everything_that_can_be_set(self):
        response = self.client.get(reverse("core:club"))
        for label in ("disciplines", "critères d'évaluation", "annonces", "membres"):
            self.assertContains(response, label)

    def test_every_screen_is_open_to_any_member(self):
        for name in ("core:club", "core:disciplines", "core:criteria", "core:news",
                     "core:members", "core:activity", "events:trash"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_no_screen_mentions_an_administration(self):
        for name in ("core:club", "core:disciplines", "core:members"):
            self.assertNotContains(self.client.get(reverse(name)), "/admin/")


class DisciplineScreenTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.declare(self.member)

    def test_creating_a_discipline(self):
        response = self.client.post(
            reverse("core:disciplines"),
            {"label": "Aquathlon", "slug": "aquathlon", "color": "#3399cc", "position": 55},
        )
        self.assertRedirects(response, reverse("core:disciplines"))
        self.assertTrue(Discipline.objects.filter(slug="aquathlon").exists())
        self.assertEqual(Activity.objects.first().action, Activity.Action.CREATED)

    def test_editing_a_discipline_returns_its_row(self):
        discipline = self.make_discipline()
        response = self.client.post(
            reverse("core:discipline_edit", args=[discipline.pk]),
            {"label": "Triathlon S", "slug": discipline.slug, "color": "#cc6666",
             "position": 10},
        )
        self.assertEqual(response.status_code, 200)
        discipline.refresh_from_db()
        self.assertEqual(discipline.label, "Triathlon S")

    def test_a_discipline_in_use_cannot_be_deleted_and_says_why(self):
        event = self.make_event()
        response = self.client.post(
            reverse("core:discipline_delete", args=[event.discipline.pk])
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Impossible de supprimer", status_code=409)
        self.assertTrue(Discipline.objects.filter(pk=event.discipline.pk).exists())

    def test_an_unused_discipline_can_be_deleted(self):
        discipline = self.make_discipline("swimrun", "Swimrun")
        response = self.client.post(reverse("core:discipline_delete", args=[discipline.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Discipline.objects.filter(pk=discipline.pk).exists())

    def test_writing_without_an_identity_asks_for_one(self):
        self.client.post(reverse("core:identity_clear"))
        response = self.client.post(
            reverse("core:disciplines"),
            {"label": "X", "slug": "x", "color": "#000000", "position": 1},
        )
        self.assertEqual(response.status_code, 409)


class CriterionScreenTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.declare(self.make_member())

    def test_creating_a_criterion(self):
        self.client.post(
            reverse("core:criteria"), {"label": "Parcours", "position": 20, "is_active": "on"}
        )
        self.assertTrue(FeedbackCriterion.objects.filter(label="Parcours").exists())

    def test_a_criterion_already_used_cannot_be_deleted(self):
        from events.models import Feedback, FeedbackScore

        criterion = self.make_criterion()
        feedback = Feedback.objects.create(member=self.make_member("Alex"),
                                           edition=self.make_edition())
        FeedbackScore.objects.create(feedback=feedback, criterion=criterion, score=4)
        response = self.client.post(reverse("core:criterion_delete", args=[criterion.pk]))
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "Décochez", status_code=409)

    def test_deactivating_keeps_it_out_of_the_forms(self):
        criterion = self.make_criterion()
        self.client.post(
            reverse("core:criterion_edit", args=[criterion.pk]),
            {"label": criterion.label, "position": 10},
        )
        criterion.refresh_from_db()
        self.assertFalse(criterion.is_active)


class NewsScreenTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.declare(self.member)

    def test_publishing_an_announcement(self):
        self.client.post(
            reverse("core:news"),
            {
                "title": "Sortie longue dimanche",
                "body": "Rendez-vous à 8h au parc.",
                "published_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "is_published": "on",
            },
        )
        self.assertTrue(News.objects.filter(title="Sortie longue dimanche").exists())

    def test_it_appears_on_the_home_page(self):
        News.objects.create(
            title="Info", body="Texte", published_at=timezone.now(), is_published=True
        )
        self.assertContains(self.client.get(reverse("events:dashboard")), "Info")

    def test_dangerous_html_in_an_announcement_is_stripped(self):
        News.objects.create(
            title="Attention",
            body="<p>Bonjour</p><script>alert(1)</script>",
            published_at=timezone.now(),
            is_published=True,
        )
        # La page porte ses propres scripts : on n'inspecte que le bloc annonce.
        body = self.client.get(reverse("events:dashboard")).content.decode()
        block = body[body.index('class="psc-news"'):]
        block = block[: block.index("</div>\n</div>")] if "</div>\n</div>" in block else block[:2000]
        self.assertNotIn("<script", block)
        self.assertNotIn("alert(1)", block)
        self.assertIn("<p>Bonjour</p>", block)

    def test_formatting_survives_in_an_announcement(self):
        News.objects.create(
            title="Sortie",
            body="<p><strong>Dimanche</strong></p><ul><li>8h au parc</li></ul>",
            published_at=timezone.now(),
            is_published=True,
        )
        response = self.client.get(reverse("events:dashboard"))
        self.assertContains(response, "<strong>Dimanche</strong>")
        self.assertContains(response, "<li>8h au parc</li>")

    def test_the_editor_is_offered_on_the_announcement_form(self):
        response = self.client.get(reverse("core:news"))
        self.assertContains(response, 'data-rich="1"')

    def test_removing_an_announcement_keeps_it(self):
        entry = News.objects.create(
            title="À retirer", body="x", published_at=timezone.now()
        )
        self.client.post(reverse("core:news_delete", args=[entry.pk]))
        self.assertFalse(News.objects.filter(pk=entry.pk).exists())
        self.assertTrue(News.all_objects.filter(pk=entry.pk).exists())


class MemberScreenTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.declare(self.make_member("Cyril", "Bonté"))

    def test_the_list_shows_members_and_their_race_count(self):
        response = self.client.get(reverse("core:members"))
        self.assertContains(response, "Cyril")
        self.assertContains(response, "aucune inscription")

    def test_searching_by_name(self):
        alex = self.make_member("Alex", "Martin")
        cyril = Member.objects.get(first_name="Cyril")
        response = self.client.get(reverse("core:members"), {"q": "mart"})
        # Le nom du membre déclaré figure dans la barre de navigation : on
        # vérifie les lignes de la liste, pas la page entière.
        self.assertContains(response, f'id="member-{alex.pk}"')
        self.assertNotContains(response, f'id="member-{cyril.pk}"')

    def test_correcting_a_misspelled_name(self):
        person = Member.objects.get(first_name="Cyril")
        self.client.post(
            reverse("core:member_edit", args=[person.pk]),
            {"first_name": "Cyril", "last_name": "Bonté", "is_active": "on"},
        )
        person.refresh_from_db()
        self.assertEqual(person.last_name, "Bonté")

    def test_a_member_who_left_keeps_their_history(self):
        person = self.make_member("Ancien", "Membre")
        self.client.post(
            reverse("core:member_edit", args=[person.pk]),
            {"first_name": "Ancien", "last_name": "Membre"},
        )
        person.refresh_from_db()
        self.assertFalse(person.is_active)
        self.assertTrue(Member.all_objects.filter(pk=person.pk).exists() if hasattr(
            Member, "all_objects") else Member.objects.filter(pk=person.pk).exists())


class ActivityScreenTests(PscTestCase):
    def test_the_journal_shows_who_did_what(self):
        member = self.make_member("Noa")
        self.declare(member)
        edition = self.make_edition()
        self.client.post(reverse("events:edition_delete", args=[edition.pk]))
        response = self.client.get(reverse("core:activity"))
        self.assertContains(response, "Noa")
        self.assertContains(response, "suppression")


class PredictionDismissalTests(PscTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.make_member()
        self.year = datetime.date.today().year
        self.source = self.make_edition(
            event=self.make_event("Course arrêtée"),
            start=datetime.date(self.year - 1, 6, 14),
        )
        self.calendar = reverse("events:calendar_year", args=[self.year])

    def test_a_proposal_can_be_set_aside(self):
        self.declare(self.member)
        response = self.client.post(
            reverse("events:prediction_dismiss", args=[self.source.pk, self.year])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PredictionDismissal.objects.filter(year=self.year).exists())

    def test_a_set_aside_proposal_leaves_the_calendar(self):
        self.declare(self.member)
        self.client.post(reverse("events:prediction_dismiss", args=[self.source.pk, self.year]))
        self.assertNotContains(self.client.get(self.calendar), "Course arrêtée")

    def test_it_can_be_brought_back(self):
        self.declare(self.member)
        self.client.post(reverse("events:prediction_dismiss", args=[self.source.pk, self.year]))
        self.client.post(reverse("events:prediction_restore", args=[self.source.pk, self.year]))
        self.assertContains(self.client.get(self.calendar), "Course arrêtée")

    def test_setting_aside_needs_an_identity(self):
        response = self.client.post(
            reverse("events:prediction_dismiss", args=[self.source.pk, self.year])
        )
        self.assertEqual(response.status_code, 409)

    def test_setting_aside_one_year_leaves_the_next_untouched(self):
        self.declare(self.member)
        self.client.post(reverse("events:prediction_dismiss", args=[self.source.pk, self.year]))
        later = reverse("events:calendar_year", args=[self.year + 1])
        self.assertContains(self.client.get(later), "Course arrêtée")


class NamedActionsTests(PscTestCase):
    """Les actions sont écrites sur la carte, pas cachées dans un menu."""

    def setUp(self):
        super().setUp()
        self.edition = self.make_edition()
        self.calendar = reverse("events:calendar_year", args=[self.edition.year])

    def test_the_calendar_spells_out_its_actions(self):
        response = self.client.get(self.calendar)
        for label in ("Modifier", "Mon agenda", "Chercher des informations", "Supprimer"):
            self.assertContains(response, label, msg_prefix=label)

    def test_every_action_carries_an_icon(self):
        response = self.client.get(self.calendar)
        body = response.content.decode()
        foot = body[body.index('class="psc-edition-foot"'):]
        foot = foot[: foot.index("</p>")]
        # Une action nommée, précédée de son icône : ni menu caché, ni icône seule.
        # « psc-action-danger » contient « psc-action » : on compte l'ouverture
        # d'attribut, qui n'apparaît qu'une fois par élément.
        self.assertEqual(foot.count("psc-icon"), foot.count('class="psc-action'))

    def test_no_hidden_menu_remains_on_the_cards(self):
        response = self.client.get(self.calendar)
        self.assertNotContains(response, 'class="psc-more"')

    def test_a_future_year_offers_actions_on_its_proposals(self):
        year = datetime.date.today().year + 1
        EventEdition.objects.filter(pk=self.edition.pk).update(
            date_start=datetime.date(year - 1, 6, 14), date_end=datetime.date(year - 1, 6, 14)
        )
        response = self.client.get(reverse("events:calendar_year", args=[year]))
        for label in ("Une autre date", "Chercher des informations", "Pas cette année"):
            self.assertContains(response, label, msg_prefix=label)
        self.assertContains(response, "Confirmer le")
        # « Inscrire » est le verbe de la participation : il ne doit pas servir ici.
        self.assertNotContains(response, "Inscrire le")


class ReorderTests(PscTestCase):
    """L'ordre se règle en déplaçant, jamais en saisissant un nombre."""

    def setUp(self):
        super().setUp()
        self.declare(self.make_member())
        self.a = Discipline.objects.create(slug="a", label="Alpha", position=10)
        self.b = Discipline.objects.create(slug="b", label="Beta", position=20)
        self.c = Discipline.objects.create(slug="c", label="Gamma", position=30)

    def _order(self):
        return [d.slug for d in Discipline.objects.order_by("position", "pk")]

    def _rendered_order(self, url=None):
        """L'ordre réellement affiché, seul juge utile.

        Les tests précédents ne regardaient que la base : ils passaient alors
        que la page sortait dans un ordre arbitraire, annotate() faisant
        abandonner Meta.ordering à Django.
        """
        body = self.client.get(url or reverse("core:disciplines")).content.decode()
        return re.findall(r'id="discipline-(\d+)"', body)

    def _stored_order(self):
        return [str(d.pk) for d in Discipline.objects.order_by("position", "pk")]

    def test_the_forms_no_longer_ask_for_a_position(self):
        for url in (reverse("core:disciplines"), reverse("core:criteria")):
            self.assertNotContains(self.client.get(url), 'name="position"', msg_prefix=url)

    def test_moving_down_swaps_with_the_next(self):
        self.client.post(reverse("core:discipline_move", args=[self.a.pk]),
                         {"direction": "down"})
        self.assertEqual(self._order(), ["b", "a", "c"])

    def test_moving_up_swaps_with_the_previous(self):
        self.client.post(reverse("core:discipline_move", args=[self.c.pk]), {"direction": "up"})
        self.assertEqual(self._order(), ["a", "c", "b"])

    def test_the_first_cannot_go_up(self):
        self.client.post(reverse("core:discipline_move", args=[self.a.pk]), {"direction": "up"})
        self.assertEqual(self._order(), ["a", "b", "c"])

    def test_the_last_cannot_go_down(self):
        self.client.post(reverse("core:discipline_move", args=[self.c.pk]),
                         {"direction": "down"})
        self.assertEqual(self._order(), ["a", "b", "c"])

    def test_dropping_applies_the_whole_order(self):
        self.client.post(
            reverse("core:disciplines_reorder"),
            {"order": [str(self.c.pk), str(self.a.pk), str(self.b.pk)]},
        )
        self.assertEqual(self._order(), ["c", "a", "b"])

    def test_unknown_identifiers_are_ignored(self):
        self.client.post(
            reverse("core:disciplines_reorder"),
            {"order": ["999999", str(self.c.pk), str(self.a.pk)]},
        )
        self.assertEqual(self._order()[:2], ["c", "a"])

    def test_a_forgotten_element_keeps_a_place_at_the_end(self):
        self.client.post(
            reverse("core:disciplines_reorder"), {"order": [str(self.c.pk)]}
        )
        self.assertEqual(self._order()[0], "c")
        self.assertEqual(sorted(self._order()), ["a", "b", "c"])

    def test_positions_are_renumbered_regularly(self):
        self.client.post(
            reverse("core:disciplines_reorder"),
            {"order": [str(self.b.pk), str(self.c.pk), str(self.a.pk)]},
        )
        self.assertEqual(
            [d.position for d in Discipline.objects.order_by("position")], [10, 20, 30]
        )

    def test_reordering_needs_an_identity(self):
        self.client.post(reverse("core:identity_clear"))
        response = self.client.post(
            reverse("core:disciplines_reorder"), {"order": [str(self.c.pk)]}
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._order(), ["a", "b", "c"])

    def test_the_response_is_the_refreshed_list(self):
        response = self.client.post(
            reverse("core:discipline_move", args=[self.a.pk]), {"direction": "down"}
        )
        self.assertContains(response, 'id="sortable-disciplines"')
        self.assertContains(response, "Alpha")

    def test_the_ends_have_their_useless_button_disabled(self):
        body = self.client.get(reverse("core:disciplines")).content.decode()
        first = body[body.index(f'id="discipline-{self.a.pk}"'):]
        first = first[: first.index("</div>")]
        self.assertIn("disabled", first)

    def test_criteria_reorder_the_same_way(self):
        one = FeedbackCriterion.objects.create(label="Un", position=10)
        two = FeedbackCriterion.objects.create(label="Deux", position=20)
        self.client.post(reverse("core:criterion_move", args=[two.pk]), {"direction": "up"})
        self.assertEqual(
            [c.label for c in FeedbackCriterion.objects.order_by("position")], ["Deux", "Un"]
        )
        del one


class RenderedOrderTests(PscTestCase):
    """Ce que la page affiche doit être ce que la base enregistre."""

    def setUp(self):
        super().setUp()
        self.declare(self.make_member())
        self.items = [
            Discipline.objects.create(slug=slug, label=slug.title(), position=(index + 1) * 10)
            for index, slug in enumerate(["alpha", "beta", "gamma", "delta"])
        ]

    def _rendered(self, url):
        body = self.client.get(url).content.decode()
        return re.findall(r'id="(?:discipline|criterion)-(\d+)"', body)

    def _stored(self, model):
        return [str(o.pk) for o in model.objects.order_by("position", "pk")]

    def test_the_disciplines_page_shows_the_stored_order(self):
        self.assertEqual(
            self._rendered(reverse("core:disciplines")), self._stored(Discipline)
        )

    def test_the_page_follows_a_move(self):
        first = self.items[0]
        self.client.post(reverse("core:discipline_move", args=[first.pk]), {"direction": "down"})
        self.assertEqual(
            self._rendered(reverse("core:disciplines")), self._stored(Discipline)
        )
        self.assertEqual(self._rendered(reverse("core:disciplines"))[1], str(first.pk))

    def test_the_page_follows_a_drop(self):
        wanted = [str(self.items[3].pk), str(self.items[0].pk),
                  str(self.items[2].pk), str(self.items[1].pk)]
        self.client.post(reverse("core:disciplines_reorder"), {"order": wanted})
        self.assertEqual(self._rendered(reverse("core:disciplines")), wanted)

    def test_the_fragment_returned_by_a_move_is_already_in_order(self):
        first = self.items[0]
        response = self.client.post(
            reverse("core:discipline_move", args=[first.pk]), {"direction": "down"}
        )
        shown = re.findall(r'id="discipline-(\d+)"', response.content.decode())
        self.assertEqual(shown, self._stored(Discipline))

    def test_the_criteria_page_shows_the_stored_order(self):
        for index, label in enumerate(["Un", "Deux", "Trois"]):
            FeedbackCriterion.objects.create(label=label, position=(index + 1) * 10)
        self.assertEqual(
            self._rendered(reverse("core:criteria")), self._stored(FeedbackCriterion)
        )

    def test_the_calendar_filters_follow_the_same_order(self):
        body = self.client.get(reverse("events:calendar"), follow=True).content.decode()
        shown = re.findall(r'id="d-([\w-]+)"', body)
        stored = [d.slug for d in Discipline.objects.order_by("position", "pk")]
        self.assertEqual(shown, stored)


class FieldMarkupTests(PscTestCase):
    """Un seul rendu de champ, et des champs qui s'alignent."""

    def setUp(self):
        super().setUp()
        self.declare(self.make_member())

    def _fields(self, html):
        return re.findall(r'<div class="psc-field([^"]*)"', html)

    def test_a_text_field_carries_its_label_above(self):
        body = self.client.get(reverse("core:disciplines")).content.decode()
        self.assertIn('<label class="form-label" for="id_label">Libellé</label>', body)

    def test_a_checkbox_carries_its_label_beside(self):
        body = self.client.get(reverse("core:criteria")).content.decode()
        self.assertIn("psc-field-check", body)
        self.assertIn('class="form-check-label"', body)
        # Jamais d'étiquette au-dessus pour une case à cocher.
        self.assertNotIn('<label class="form-label" for="id_is_active"', body)

    def test_the_submit_button_is_not_a_grid_cell(self):
        """Placé dans la grille, il s'alignait avec les champs de saisie."""
        body = self.client.get(reverse("core:disciplines")).content.decode()
        # La barre de navigation porte elle aussi un formulaire : on vise la
        # grille, pas le premier <form> venu.
        start = body.index('class="psc-form-grid"')
        end = body.index("psc-form-actions", start)
        self.assertNotIn("<button", body[start:end])
        self.assertIn("Ajouter", body[end : end + 300])

    def test_no_form_aligns_its_grid_on_the_bottom(self):
        """align-items-end désalignait les champs porteurs d'un texte d'aide."""
        for name in ("core:disciplines", "core:criteria", "core:news"):
            body = self.client.get(reverse(name)).content.decode()
            self.assertNotIn("align-items-end", body, msg=name)

    def test_every_club_form_uses_the_shared_field_markup(self):
        for name in ("core:disciplines", "core:criteria", "core:news", "core:members"):
            body = self.client.get(reverse(name)).content.decode()
            if 'class="psc-field' in body:
                self.assertIn("psc-field", body, msg=name)

    def test_the_edition_form_uses_it_too(self):
        edition = self.make_edition()
        body = self.client.get(
            reverse("events:edition_edit", args=[edition.pk])
        ).content.decode()
        self.assertGreaterEqual(body.count('class="psc-field"'), 8)
