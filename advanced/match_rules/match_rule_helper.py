import copy
import json
from getpass import getpass
from typing import Dict, List, Tuple

import ipywidgets as widgets
from cognite.experimental import CogniteClient
from IPython.display import display
from regex import regex

ID = "id"
DEFAULT = "default"
MATCHES = "Matches"
MATCH_LISTS = "User match list"

READY = "Ready"
GENERATING_RULES = "Generating rules"
APPLYING_RULES = "Applying rules"

UNHANDLED = "Unhandled"
CONFIRMED = "Confirmed"
DELETED = "Deleted"

NO_CHANGE = "No change"
APPLY_CHANGES = "Apply changes"

RULE_OUTPUT = "rule_output"


class ResourceHelper:
    def __init__(self, client: CogniteClient):
        self.client = client

        self.root_assets = [a for a in self.client.assets.list(root=True, limit=-1) if "asset" not in a.name][:100]
        self.root_asset_selector = widgets.Dropdown(
            options=[(a.name, a.id) for a in self.root_assets],
            description="Select root asset"
        )

    def select_root_asset(self):
        display(self.root_asset_selector)

    def get_timeseries(self, limit=-1):
        root_id = self.root_asset_selector.value
        return [t.dump() for t in self.client.time_series.list(limit=limit, root_asset_ids=[root_id])]

    def get_assets(self, limit=-1):
        root_id = self.root_asset_selector.value
        return [a.dump() for a in self.client.assets.list(limit=limit, root_ids=[root_id])]


class MatchRuleHelper:
    def __init__(self, project: str):
        self.project = project
        self.client = CogniteClient(
            project=project,
            api_key=getpass(f"Please enter {project} API-KEY: "),
            client_name="dshub"
        )
        self.resource_helper = ResourceHelper(self.client)

        self.sources = []
        self.source_entities = []
        self.source_by_id = {}
        self.source_all_fields = []
        self.source_fields = []
        self.source_id = ID
        self.reduced_sources = []

        self.targets = []
        self.target_entities = []
        self.target_by_id = {}
        self.target_all_fields = []
        self.target_fields = []
        self.target_id = ID
        self.reduced_targets = []

        self.user_match_lists = {DEFAULT: []}
        self.user_unambiguous = {DEFAULT: []}
        self.user_ambiguous = {DEFAULT: []}
        self.user_match_editor = UserMatchEditor(self)

        self.rule_editor = RuleEditor(self)

        self.comparator = MatchComparator(self)

    def set_helper_resources(self, limit=-1):
        self.set_sources(self.resource_helper.get_timeseries(limit))
        self.set_targets(self.resource_helper.get_assets(limit))

    def add_cdf_matches(self):
        self.add_match_set("cdf_matches", [(k, v.get("asset_id")) for k, v in self.source_by_id.items() if v.get("asset_id") in self.target_by_id])

    def set_targets(self, targets):
        self.targets = targets
        self.target_entities = [MatchRuleHelper.flatten(target) for target in self.targets]
        self.target_all_fields = list({k for k in entity} for entity in self.target_entities)
        self.target_by_id = {t[self.target_id]: t for t in self.target_entities}
        self.reduced_targets = MatchRuleHelper.reduced_entities(self.target_entities, self.target_fields)
        self.user_match_editor.set_target_entities(self.target_entities)

    def set_target_fields(self, target_fields: List[str]):
        self.target_fields = list({self.target_id} | set(target_fields))
        self.reduced_targets = MatchRuleHelper.reduced_entities(self.target_entities, self.target_fields)
        self.user_match_editor.set_target_fields(target_fields)
        self.rule_editor.target_field_selector.set_fields(target_fields)

    def set_sources(self, sources):
        self.sources = sources
        self.source_entities = [MatchRuleHelper.flatten(source) for source in self.sources]
        self.source_all_fields = list({k for k in entity} for entity in self.source_entities)
        self.source_by_id = {s[self.source_id]: s for s in self.source_entities}
        self.reduced_sources = MatchRuleHelper.reduced_entities(self.source_entities, self.source_fields)
        self.user_match_editor.set_source_entities(self.source_entities)

    def set_source_fields(self, source_fields: List[str]):
        self.source_fields = list({self.source_id} | set(source_fields))
        self.reduced_sources = MatchRuleHelper.reduced_entities(self.source_entities, self.source_fields)
        self.user_match_editor.set_source_fields(source_fields)
        self.rule_editor.source_field_selector.set_fields(source_fields)

    def add_match(self, list_name: str, match: Tuple):
        match_list = self.user_match_lists[list_name]
        if None in match or match in match_list:
            return False
        match_list.append(match)
        self.user_unambiguous[list_name], self.user_ambiguous[list_name] = MatchRuleHelper.calculate_ambiguous_and_not(match_list)
        self.user_match_editor.set_match_options()
        self.comparator.set_compare_options(None)

    def remove_match(self, list_name: str, match: Tuple):
        match_list = self.user_match_lists[list_name]
        if match not in match_list:
            return False
        match_list.remove(match)
        self.user_match_editor.set_match_options()
        self.comparator.set_compare_options(None)

    def get_match_options(self, tuple_list: List[Tuple], source_field: str, target_field: str):
        return [
            (
                (self.source_by_id[match[0]].get(source_field), self.target_by_id[match[1]].get(target_field)),
                match
            )
            for match in tuple_list
        ]

    def get_source_tuple(self, id, field):
        return (self.source_by_id[id][field], id)

    def get_target_tuple(self, id, field):
        return (self.target_by_id[id][field], id)

    def edit_user_matches(self):
        self.user_match_editor.display()

    def edit_rules(self):
        display(self.rule_editor.widget)

    def add_match_set(self, name, matches):
        if name in self.user_match_lists:
            print(f"{name} is already a user match list")
            return
        matches = [m if isinstance(m, tuple) else MatchRuleHelper.dict_to_match(m) for m in matches]
        self.user_match_lists[name] = matches
        self.user_match_editor.match_list_selector.options=[name for name in self.user_match_lists]
        self.rule_editor.user_match_list_widget.options=[name for name in self.user_match_lists]
        good, bad = MatchRuleHelper.calculate_ambiguous_and_not(matches)
        self.user_unambiguous[name] = good
        self.user_ambiguous[name] = bad

        self.comparator.set_compare_options(None)

    def compare(self):
        display(self.comparator.widget)

    def to_json(self):
        return {
            "project": self.project,
            "sources": self.sources,
            "source_fields": self.source_fields,
            "targets": self.targets,
            "target_fields": self.target_fields,
            "match_lists": {k: [list(t) for t in v] for k, v in self.user_match_lists.items()},
            "rules": self.rule_editor.rules,
            "deleted_rules": self.rule_editor.deleted_rules,
            "rule_status": self.rule_editor.status_by_rule_string
        }

    @staticmethod
    def from_json(d):
        rule_helper = MatchRuleHelper(d["project"])
        rule_helper.set_sources(d["sources"])
        rule_helper.set_targets(d["targets"])
        rule_helper.set_source_fields(d["source_fields"])
        rule_helper.set_target_fields(d["target_fields"])
        for name, match_list in d["match_lists"].items():
            rule_helper.add_match_set(name, [tuple(l) for l in match_list])
        rule_helper.rule_editor.add_rules(d["rules"])
        rule_helper.rule_editor.deleted_rules = d["deleted_rules"]
        rule_helper.rule_editor.status_by_rule_string = d["rule_status"]
        return rule_helper

    @staticmethod
    def calculate_ambiguous_and_not(matches: List[Tuple]) -> Tuple[List[Tuple], List]:
        match_dict = {}
        ambi = []
        disambi = []
        for match in matches:
            if match[0] not in match_dict:
                match_dict[match[0]] = match[1]
            else:
                if match_dict[match[0]] != match[1]:
                    match_dict[match[0]] = None
        for k, v in match_dict.items():
            if v is None:
                ambi.append(k)
            else:
                disambi.append((k, v))
        return disambi, ambi


    @staticmethod
    def reduced_entities(entities, entity_fields):
        return [{k: e.get(k) for k in entity_fields} for e in entities]

    @staticmethod
    def flatten(entity: Dict):
        flattened = {
            **{k: v for k, v in entity.items() if not isinstance(v, (dict, list))},
            **{
                "metadata." + k: entity.get("metadata").get(k) for k in entity.get("metadata", {})
            }
        }
        return flattened

    @staticmethod
    def match_to_dict(match: Tuple) -> Dict:
        return {"sourceId": match[0], "targetId": match[1]}

    @staticmethod
    def dict_to_match(d: Dict) -> Tuple:
        return (d.get("sourceId") or d.get("source", {}).get(ID)), (d.get("targetId") or d.get("target", {}).get(ID))


class EntitySelector:
    def __init__(self, title: str, entities: List[Dict], display_field: str, id_field: str, style: Dict=None, layout=None):
        self.title = title
        self.entities = entities
        self.filtered = set()
        self.display_field = display_field
        self.id_field = id_field
        self.limit = 100
        self.substring = ""

        self.entity_dropdown = widgets.Dropdown(
            options=self.get_options(),
            value=None,
            description=self.title,
            disabled=False,
            style=style,
            layout=layout
        )
        self.widget = self.entity_dropdown

    def get_options(self):
        all_options = [
            (e.get(self.display_field, "No value"), e[self.id_field])
            for e in self.entities if e[self.id_field] not in self.filtered
        ]
        return [e for e in all_options if self.substring in str(e[0])][:self.limit]

    def _set_options(self):
        options = self.get_options()
        if self.entity_dropdown.value not in [o[1] for o in options]:
            self.entity_dropdown.value = None
        self.entity_dropdown.options = options

    def set_filtered(self, filtered):
        self.filtered = filtered
        self._set_options()

    def set_display_field(self, display_field):
        self.display_field = display_field
        self._set_options()

    def get_entity_id(self):
        return self.entity_dropdown.value

    def set_substring(self, substring):
        self.substring = substring
        self._set_options()

    def set_entities(self, entities):
        self.entities = entities
        self._set_options()


class FieldSelector:
    def __init__(self, title: str, fields: List[str], id: str, style=None, layout=None):
        self.title = title
        self.id = id
        self.fields = list({self.id} | set(fields))
        self.widget = widgets.Dropdown(
            options=self.fields,
            value=self.id,
            description=self.title,
            disabled=False,
            style=style,
            layout=layout
        )

    def set_fields(self, fields: List[str]):
        self.fields = list({self.id} | set(fields))
        if self.widget.value not in self.fields:
            self.widget.value = self.id
        self.widget.options = self.fields

    def get_field(self):
        return self.widget.value

    def observe(self, action):
        self.widget.observe(handler=action, names=["value"])


class UserMatchEditor:
    def __init__(self, match_rule_helper: MatchRuleHelper):
        self.match_rule_helper = match_rule_helper

        style = {'description_width': '20%'}
        lay50 = widgets.Layout(width="50%")
        lay25 = widgets.Layout(width="25%")

        self.source_selector = EntitySelector(
            "Source",
            self.match_rule_helper.source_entities,
            self.match_rule_helper.source_id,
            self.match_rule_helper.source_id,
            style=style,
            layout=lay50
        )
        self.source_field_selector = FieldSelector(
            "Source field",
            self.match_rule_helper.source_fields,
            self.match_rule_helper.source_id,
            style=style,
            layout=lay50
        )

        self.target_selector = EntitySelector(
            "Target",
            self.match_rule_helper.target_entities,
            self.match_rule_helper.target_id,
            self.match_rule_helper.target_id,
            style=style,
            layout=lay50
        )

        self.target_field_selector = FieldSelector(
            "Target field",
            self.match_rule_helper.target_fields,
            self.match_rule_helper.target_id,
            style=style,
            layout=lay50
        )

        self.match_list_selector = widgets.Dropdown(
            options=[list_name for list_name in self.match_rule_helper.user_match_lists],
            value=DEFAULT,
            description=MATCH_LISTS,
            disabled=False,
            style=style,
            layout=lay50
        )

        self.match_selector = widgets.Dropdown(
            options=self._get_match_options(),
            value=None,
            description=MATCHES,
            disabled=False,
            style=style,
            layout=lay50
        )

        self.add_match_button = widgets.Button(description="Add match", style=style, layout=lay50)
        self.remove_match_button = widgets.Button(description="Remove match", style=style, layout=lay50)

        self.add_match_button.on_click(self._add_match)
        self.remove_match_button.on_click(self._remove_match)

        self.source_search = widgets.Text(
            value='',
            placeholder='substring',
            description='Search sources:',
            disabled=False,
            style=style, layout=lay50
        )
        self.target_search = widgets.Text(
            value='',
            placeholder='substring',
            description='Search targets:',
            disabled=False,
            style=style, layout=lay50
        )

        self.source_search.observe(
            handler=lambda x: self.source_selector.set_substring(self.source_search.value),
            names=["value"]
        )
        self.target_search.observe(
            handler=lambda x: self.target_selector.set_substring(self.target_search.value),
            names=["value"]
        )

        self.source_field_selector.observe(
            lambda x: self.source_selector.set_display_field(
                self.source_field_selector.get_field()) or self.set_match_options()
        )
        self.target_field_selector.observe(
            lambda x: self.target_selector.set_display_field(
                self.target_field_selector.get_field()) or self.set_match_options()
        )

        self.match_list_selector.observe(handler=self.set_match_options, names=["value"])

        self.widget = widgets.VBox([
            widgets.HBox([self.source_field_selector.widget, self.target_field_selector.widget]),
            widgets.HBox([self.source_search, self.target_search]),
            widgets.HBox([self.source_selector.widget, self.target_selector.widget]),
            widgets.HBox([self.match_list_selector, self.match_selector]),
            widgets.HBox([self.add_match_button, self.remove_match_button]),
        ])

    def _get_match_options(self, limit: int = 100):
        return self.match_rule_helper.get_match_options(
            self.match_rule_helper.user_match_lists[self.match_list_selector.value],
            self.source_field_selector.get_field(),
            self.target_field_selector.get_field()
        )[:limit]

    def set_match_options(self, button=None):
        options = self._get_match_options()
        if self.match_selector.value not in options:
            self.match_selector.value = None
        self.match_selector.options = options

    def _add_match(self, button):
        source_id = self.source_selector.get_entity_id()
        target_id = self.target_selector.get_entity_id()
        match = (source_id, target_id)
        self.match_rule_helper.add_match(self.match_list_selector.value, match)

    def _remove_match(self, button):
        match = self.match_selector.value
        self.match_rule_helper.remove_match(self.match_list_selector.value, match)

    def display(self):
        display(self.widget)

    def set_source_fields(self, fields):
        self.source_field_selector.set_fields(fields)

    def set_target_fields(self, fields):
        self.target_field_selector.set_fields(fields)

    def set_source_entities(self, sources):
        self.source_selector.set_entities(sources)

    def set_target_entities(self, targets):
        self.target_selector.set_entities(targets)


class RuleEditor:
    def __init__(self, match_rule_helper: MatchRuleHelper):
        self.match_rule_helper = match_rule_helper
        self.client = self.match_rule_helper.client

        self.status_by_rule_string = {}
        self.rules = []
        self.deleted_rules = []
        self.status = "Ready"
        self.delete_changes = set()
        self.uncalculated_rules = False

        self.matches = []
        self.ambiguous_matches = []

        self.applied_rules = []

        style = {'description_width': '20%'}
        style_2 = {'description_width': '40%'}
        lay100 = widgets.Layout(width="100%")
        lay50 = widgets.Layout(width="50%")
        lay25 = widgets.Layout(width="25%")

        self.user_match_list_widget = widgets.Dropdown(
            options=[list_name for list_name in self.match_rule_helper.user_match_lists],
            value=DEFAULT,
            description=MATCH_LISTS,
            disabled=False,
            style=style,
            layout=lay50
        )

        self.generate_rules_button = widgets.Button(
            description="Generate rules from list", style=style, layout=lay50
        )

        self.generate_rules_button.on_click(self._check_status(self._generate_rules))

        self.status_widget = widgets.HTML(
            value=f"<b>{self.status}</b>",
            placeholder="status",
            description="Status:",
            style=style,
            layout=lay50
        )

        self.rule_info = {}

        self.rule_widget = widgets.Dropdown(
            options=[],
            value=None,
            description="Rule #",
            style=style,
            layout=lay50
        )

        self.source_field_selector = FieldSelector(
            "Source field", self.match_rule_helper.source_fields, self.match_rule_helper.source_id,
            style=style,
            layout=lay50
        )
        self.target_field_selector = FieldSelector(
            "Target field", self.match_rule_helper.target_fields, self.match_rule_helper.target_id,
            style=style,
            layout=lay50
        )

        self.source_field_selector.observe(self._update_rule_matches_and_info)
        self.target_field_selector.observe(self._update_rule_matches_and_info)

        self.rule_matches_widget = widgets.Dropdown(
            options=[],
            value=None,
            description="Rule matches",
            style=style,
            layout=lay50
        )

        self.number_of_matches_widget = widgets.HTML(value=None, description="# Matches:", style=style_2, layout=lay25)
        self.priority_widget = widgets.HTML(value=None, description="Priority: ", style=style_2, layout=lay25)
        self.source_match_widget = widgets.HTML(value=None, description="Source:", style=style, layout=lay50)
        self.target_match_widget = widgets.HTML(value=None, description="Target:", style=style, layout=lay50)

        self.rule_matches_widget.observe(handler=self._update_rule_match_info, names=["value"])
        self.rule_widget.observe(handler=self._update_rule_matches_and_info, names="value")

        self.rule_action_widget = widgets.Dropdown(
            description="Status:",
            options=[UNHANDLED, CONFIRMED, DELETED],
            value=UNHANDLED,
            style=style,
            layout=lay50
        )
        self.rule_action_widget.observe(handler=self._rule_action, names=["value"])

        self.apply_change_button = widgets.Button(description=NO_CHANGE, style=style, layout=lay50)
        self.apply_change_button.on_click(self._check_status(self._apply_changes))

        self.conflict_dropdown = widgets.Dropdown(description="0 conflicting rules", style=style, layout=lay50)
        self.overlap_dropdown = widgets.Dropdown(description="0 overlapping rules", style=style, layout=lay50)

        self.rule_info_widget = widgets.VBox(
            [
                widgets.HBox([self.rule_widget, self.rule_action_widget]),
                widgets.HBox([self.rule_matches_widget, self.number_of_matches_widget, self.priority_widget]),
                widgets.HBox([self.conflict_dropdown, self.overlap_dropdown]),
                widgets.HBox([self.source_match_widget, self.target_match_widget]),
            ]
        )

        self.user_match_list_widget.observe(handler=self._update_rule_info_widget, names=["value"])

        self.fancy_match = widgets.HTML(value=None, layout=lay100)

        self.widget = widgets.VBox(
            [
                widgets.HBox([self.user_match_list_widget, self.status_widget]),
                widgets.HBox([self.generate_rules_button, self.apply_change_button]),
                widgets.HBox([self.source_field_selector.widget, self.target_field_selector.widget]),
                self.rule_info_widget,
                self.fancy_match
            ]
        )

    def display_fancy_match(self):
        rule_index = self.rule_widget.value
        rule_match = self.rule_matches_widget.value
        if None in [rule_match, rule_index]:
            self.fancy_match.value = ""
            return
        rule = self.rules[rule_index]
        options = [t[1] for t in self.rule_matches_widget.options]
        match_index = options.index(rule_match)
        info = self.rule_info[str(rule)]
        extractors = _label_groups(copy.deepcopy(rule["extractors"]), rule["conditions"])
        self.fancy_match.value = _color_match(extractors, info["matches"][match_index])

    def _set_status(self, value):
        self.status = value
        self.status_widget.value = f"<b>{self.status}</b>"

    def add_rule(self, rule):
        string = str(rule)
        if string in self.status_by_rule_string:
            return False
        self.status_by_rule_string[string] = UNHANDLED
        self.rules.append(rule)

    def _check_status(self, f):
        return lambda x: self.status == READY and f(x)

    def _generate_rules(self, button):
        self._set_status(GENERATING_RULES)
        sources, targets = self.match_rule_helper.reduced_sources, self.match_rule_helper.reduced_targets
        matches = self.match_rule_helper.user_match_lists[self.user_match_list_widget.value]
        matches = [MatchRuleHelper.match_to_dict(m) for m in matches]

        suggest_response = self.client.match_rules.suggest(sources, targets, matches)
        suggest_result = suggest_response.result
        for rule in suggest_result["rules"]:
            self.add_rule(rule)

        self._apply_rules(None)

    def _apply_rules(self, button=None):
        self._set_status(APPLYING_RULES)
        self._clean_up_deleted_rules()
        sources, targets = self.match_rule_helper.reduced_sources, self.match_rule_helper.reduced_targets
        apply_response = self.client.match_rules.apply(sources, targets, self.rules)

        self.apply_result = apply_response.result
        self.fancy_rules = apply_response.rules
        self._update_rule_info(self.apply_result)
        self.uncalculated_rules = False
        self.match_rule_helper.comparator.set_compare_options(None)
        self._set_status(READY)

    def _update_rule_info(self, apply_result):
        self.rule_info = {str(rule): apply_result["items"][i] for i, rule in enumerate(self.rules)}

        matches = []
        for info in self.rule_info.values():
            info["match_tuples"] = [MatchRuleHelper.dict_to_match(d) for d in info["matches"]]
            matches.extend(info["match_tuples"])
        self.matches, self.ambiguous_matches = MatchRuleHelper.calculate_ambiguous_and_not(matches)
        self._update_rule_info_widget(None)

    def _update_rule_info_widget(self, _):
        rule_options = [i for i, _ in enumerate(self.rules)]
        if not rule_options:
            self.rule_widget.value = None
        elif self.rule_widget.value not in rule_options:
            self.rule_widget.value = None
            self.rule_widget.options = rule_options
            self.rule_widget.value = rule_options[0]
        self.rule_widget.options = rule_options
        self._update_rule_matches_and_info(None)

    def _update_rule_matches_and_info(self, _):
        limit = 100
        rule_number = self.rule_widget.value
        if rule_number is None:
            self.rule_matches_widget.value = None
            self.rule_matches_widget.options = []
            self.number_of_matches_widget.value = ""
            self.priority_widget.value = ""
            self.rule_action_widget.value = UNHANDLED
            conflicts = []
            overlaps = []
        else:
            rule = self.rules[rule_number]
            rule_string = str(rule)
            match_tuples = self.rule_info[rule_string]["match_tuples"]
            options = self.match_rule_helper.get_match_options(
                match_tuples,
                self.source_field_selector.get_field(),
                self.target_field_selector.get_field()
            )[:limit]
            if self.rule_matches_widget.value not in options:
                self.rule_matches_widget.value = None
            self.rule_matches_widget.options = options
            info = self.rule_info[str(self.rules[rule_number])]
            self.number_of_matches_widget.value = str(info["numberOfMatches"])
            self.priority_widget.value = str(rule["priority"])
            self.rule_action_widget.value = self.status_by_rule_string.get(rule_string, UNHANDLED)

            conflicts = self.rule_info[rule_string].get("conflicts")
            overlaps = self.rule_info[rule_string].get("overlaps")
        self.conflict_dropdown.description = f"{len(conflicts)} conflicting rules"
        self.conflict_dropdown.value = None
        self.conflict_dropdown.options = [RuleEditor.conflict_to_string(c) for c in conflicts]
        if conflicts:
            self.conflict_dropdown.value = self.conflict_dropdown.options[0]
        self.overlap_dropdown.description = f"{len(overlaps)} overlapping rules"
        self.overlap_dropdown.value = None
        self.overlap_dropdown.options = [RuleEditor.conflict_to_string(o) for o in overlaps]
        if overlaps:
            self.overlap_dropdown.value = self.overlap_dropdown.options[0]

    def _update_rule_match_info(self, _):
        rule_number = self.rule_widget.value
        match = self.rule_matches_widget.value
        if rule_number is None or match is None:
            self.source_match_widget.value = ""
            self.target_match_widget.value = ""
        else:
            self.source_match_widget.value = json.dumps(
                {
                    k: v for k, v in self.match_rule_helper.source_by_id[match[0]].items()
                    if k in self.match_rule_helper.source_fields
                },
                indent=2
            )
            self.target_match_widget.value = json.dumps(
                {
                    k: v for k, v in self.match_rule_helper.target_by_id[match[1]].items()
                    if k in self.match_rule_helper.target_fields
                },
                indent=2
            )
        self.display_fancy_match()

    def _rule_action(self, _):
        rule_i = self.rule_widget.value
        if rule_i is not None:
            rule = self.rules[rule_i]
            self.status_by_rule_string[str(rule)] = self.rule_action_widget.value
            if self.rule_action_widget.value == DELETED:
                self.delete_changes.add(rule_i)
            elif rule_i in self.delete_changes:
                self.delete_changes.remove(rule_i)
            self._notice_changes()

    def _notice_changes(self, _=None):
        if self.delete_changes or self.uncalculated_rules:
            self.apply_change_button.description = APPLY_CHANGES
        else:
            self.apply_change_button.description = NO_CHANGE

    def _clean_up_deleted_rules(self):
        self.deleted_rules.extend([r for i, r in enumerate(self.rules) if i in self.delete_changes])
        self.rules = [r for i, r in enumerate(self.rules) if i not in self.delete_changes]
        self.delete_changes = set()
        self._notice_changes()

    def _apply_changes(self, _):
        if self.apply_change_button.description == NO_CHANGE:
            return False
        self._apply_rules(None)

    def add_rules(self, rules: List[Dict], hard=False):
        if self.status != READY:
            print("Not ready")
            return False
        old_len_rules = len(self.rules)
        for rule in rules:
            if hard and self.status_by_rule_string.get(str(rule)) == DELETED:
                self.status_by_rule_string.pop(str(rule))
            self.add_rule(rule)
        if old_len_rules != len(self.rules):
            self.uncalculated_rules = True
            self._apply_rules()

    @staticmethod
    def conflict_to_string(conflict):
        return f"Rule#{conflict['ruleIndex']}: {conflict['multiplicity']}"


class MatchComparator:
    def __init__(self, match_rule_helper: MatchRuleHelper):
        self.match_rule_helper = match_rule_helper
        self.match_lists = self.match_rule_helper.user_match_lists
        self.rule_editor = self.match_rule_helper.rule_editor
        self.source_field_selector = self.match_rule_helper.user_match_editor.source_field_selector
        self.target_field_selector = self.match_rule_helper.user_match_editor.target_field_selector

        style = {'description_width': '20%'}
        self.first_list_selector = widgets.Dropdown(
            options=self._get_list_options(), value=RULE_OUTPUT, layout=widgets.Layout(width="50%"), style=style)
        self.second_list_selector = widgets.Dropdown(
            options=self._get_list_options(), value=DEFAULT, layout=widgets.Layout(width="50%"), style=style
        )

        self.agreed_list = widgets.Dropdown(layout=widgets.Layout(width="99%"), style=style)
        self.first_only_list = widgets.Dropdown(layout=widgets.Layout(width="50%"), style=style)
        self.first_ambiguous = widgets.Dropdown(layout=widgets.Layout(width="50%"), style=style)
        self.second_only_list = widgets.Dropdown(layout=widgets.Layout(width="50%"), style=style)
        self.second_ambiguous = widgets.Dropdown(layout=widgets.Layout(width="50%"), style=style)
        self.disagreement_list = widgets.Dropdown(layout=widgets.Layout(width="99%"), style=style)

        self.first_disagreed = widgets.HTML(description="first says:", layout=widgets.Layout(width="50%"), style=style)
        self.second_disagreed = widgets.HTML(
            description="second says:", layout=widgets.Layout(width="50%"), style=style
        )

        self.first_list_selector.observe(self._combine_lists, names=["value", "options"])
        self.second_list_selector.observe(self._combine_lists, names=["value", "options"])

        self.disagreement_list.observe(self._select_disagreed, names=["value", "options"])

        self.widget = widgets.VBox([
            widgets.HBox([self.first_list_selector, self.second_list_selector]),
            widgets.HBox([self.first_only_list, self.second_only_list]),
            widgets.HBox([self.first_ambiguous, self.second_ambiguous]),
            self.agreed_list,
            self.disagreement_list,
            widgets.HBox([self.first_disagreed, self.second_disagreed]),
        ])

    def set_compare_options(self, _):
        self.first_list_selector.value = RULE_OUTPUT
        self.second_list_selector.value = DEFAULT
        self.first_list_selector.options = self._get_list_options()
        self.second_list_selector.options = self._get_list_options()

    def _get_list_options(self):
        return [RULE_OUTPUT] + [k for k in self.match_lists]

    def _get_matches(self, key):
        if key == RULE_OUTPUT:
            return self.rule_editor.matches, self.rule_editor.ambiguous_matches
        else:
            return self.match_rule_helper.user_unambiguous[key], self.match_rule_helper.user_ambiguous[key]

    def _combine_lists(self, _=None):
        first = self.first_list_selector.value
        second = self.second_list_selector.value
        source_field = self.source_field_selector.get_field()
        target_field = self.target_field_selector.get_field()

        matches = {key: self._get_matches(key) for key in [first, second]}

        self.first_ambiguous.value = None
        options = [self.match_rule_helper.get_source_tuple(x, source_field) for x in matches[first][1]]
        self.first_ambiguous.options = options[:100]
        self.first_ambiguous.description = f"{len(options)} ambiguous"

        self.second_ambiguous.value = None
        options = [self.match_rule_helper.get_source_tuple(x, source_field) for x in matches[second][1]]
        self.second_ambiguous.options = options[:100]
        self.second_ambiguous.description = f"{len(options)} ambiguous"

        match_dicts = {key: {m[0]: m[1] for m in matches[key][0]} for key in [first, second]}

        agreed = [(k, v) for k, v in match_dicts[first].items() if match_dicts[second].get(k)==v]
        disagreed = [
            k for k, v in match_dicts[first].items() if match_dicts[second].get(k) not in {None, v}
        ]
        just_first = [(k, v) for k, v in match_dicts[first].items() if k not in match_dicts[second]]
        just_second = [(k, v) for k, v in match_dicts[second].items() if k not in match_dicts[first]]

        self.agreed_list.value = None
        self.agreed_list.options = self.match_rule_helper.get_match_options(agreed[:100], source_field, target_field)
        self.agreed_list.description = f"Agree on {len(agreed)} matches:"

        self.disagreement_list.value = None
        self.disagreement_list.options = [
            self.match_rule_helper.get_source_tuple(x, source_field) for x in disagreed[:100]
        ]
        self.disagreement_list.description = f"Disagree on {len(disagreed)} matches:"

        self.first_only_list.value = None
        options = self.match_rule_helper.get_match_options(just_first, source_field, target_field)
        self.first_only_list.options = options[:100]
        self.first_only_list.description = f"{len(options)} unique:"

        self.second_only_list.value = None
        options = self.match_rule_helper.get_match_options(just_second, source_field, target_field)
        self.second_only_list.options = options[:100]
        self.second_only_list.description = f"{len(options)} unique:"

    def _select_disagreed(self, _=None):
        source_id = self.disagreement_list.value
        if source_id is None:
            return
        first = self.first_list_selector.value
        second = self.second_list_selector.value
        matches = {key: self._get_matches(key) for key in [first, second]}

        first_target = ([k[1] for k in matches[first][0] if k[0] == source_id] + [None])[0]
        second_target = ([k[1] for k in matches[second][0] if k[0] == source_id] + [None])[0]

        if None in (first_target, second_target):
            return
        first_entity = self.match_rule_helper.target_by_id[first_target]
        self.first_disagreed.value = json.dumps(
            {k: first_entity.get(k) for k in self.match_rule_helper.target_fields}, indent=2
        )

        second_entity = self.match_rule_helper.target_by_id[second_target]
        self.second_disagreed.value = json.dumps(
            {k: second_entity.get(k) for k in self.match_rule_helper.target_fields}, indent=2
        )


# Copied and modified from sdk
def _color_match(extractors: List[Dict], match: Dict):
    columns = sorted(list({(extractor["entitySet"][:-1], extractor["field"]) for extractor in extractors}))  # order?
    patterns = {
        (extractor["entitySet"][:-1], extractor["field"]): extractor["pattern"].strip("^$")
        for extractor in extractors
        if extractor["extractorType"] == "regex"
    }
    formatted = {
        "source": copy.copy(match.get("source")),
        "target": copy.copy(match.get("target")),
    }
    for extractor in extractors:
        if extractor["extractorType"] != "regex":
            continue
        source_target = extractor["entitySet"][:-1]  # singular
        field = extractor["field"]
        regex_match = regex.match(extractor["pattern"], match.get(source_target, {}).get(field, ""))
        if not regex_match:
            print(
                "Unexpected lack of match of ", extractor["pattern"], match.get(source_target), field,
            )
            continue
        formatted_field = regex_match.expand(extractor["restorePattern"])
        formatted[source_target][field] = formatted_field

    html = ",  ".join(
        [f"{source_target}.{field}: {formatted[source_target][field]}" for source_target, field in columns]
    )
    return html


# Copied from sdk
def _label_groups(extractors: List[Dict], conditions: List[Dict]):
    colors = [
        "".join(f"{int(round(rgb*255)):02x}" for rgb in color)
        for color in [
            [0, 0.3470, 0.841],
            [0.9, 0.3250, 0.098],
            [0.9290, 0.694, 0.125],
            [0.4940, 0.184, 0.556],
            [0.4660, 0.674, 0.188],
            [0.3010, 0.745, 0.933],
            [0.6350, 0.078, 0.184],
        ]
    ]

    for extractor in extractors:
        extractor["groupLabel"] = {}

    for ci, condition in enumerate(conditions):
        if condition["conditionType"] != "equals":
            continue
        for ei, part in condition["arguments"]:
            extractor = extractors[ei]
            extractor["groupLabel"][part + 1] = ci  # 1-based

    for extractor in extractors:
        if extractor["extractorType"] != "regex":
            continue
        group_counter = 0

        def color_group(_):
            nonlocal group_counter, extractor
            group_counter += 1
            label_ix = extractor["groupLabel"].get(group_counter)
            if label_ix is not None:
                color = colors[label_ix % len(colors)]
                return f"<font color='#{color}'>\\g<{group_counter}></font>"
            else:
                return f"\\g<{group_counter}>"

        extractor["restorePattern"] = (
            "<font color='#666'>" + regex.sub(r"\(.*?\)", color_group, extractor["pattern"].strip("$^")) + "</font>"
        )

    return extractors
