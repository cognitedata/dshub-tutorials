import itertools
from typing import Dict, List

import numpy as np
import pandas as pd
from cognite.datastudio.entity_matcher import EntityMatcher, Model


def _chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i : i + n]


def _get_new_average(row):
    return sum(score * num_matches for score, num_matches in zip(row["avgScore"], row["numMatches"])) / np.sum(
        row["numMatches"]
    )


def chunk_create_rules_df(
    entity_matcher: EntityMatcher, matches: List[Dict], size: int = 100000, verbose: bool = True
) -> pd.DataFrame:
    rules_list = []

    for chunk_index, matches_chunk in enumerate(_chunks(matches, size)):
        chunk_rules = entity_matcher.create_rules(matches_chunk)
        list(
            map(
                lambda d: d.update(
                    {"matchIndex": list(map(lambda index: index + size * chunk_index, d["matchIndex"]))}
                ),
                chunk_rules,
            )
        )
        rules_list.extend(chunk_rules)
        if verbose:
            print("Finished with chunk nr.", chunk_index, ".")

    pd_rules = pd.DataFrame.from_dict(rules_list).groupby(["inputPattern", "predictPattern"], as_index=False).agg(list)
    pd_rules["avgScore"] = pd_rules.apply(_get_new_average, axis=1)
    pd_rules["numMatches"] = pd_rules["numMatches"].apply(lambda x: sum(x))
    pd_rules["matchIndex"] = pd_rules["matchIndex"].apply(lambda x: pd.Index(itertools.chain(*x)))

    return pd_rules


def chunk_predict(model: Model, input_list: List[str], size: int = 100000, verbose: bool = True):
    predicted_matches = []
    for chunk_index, input_chunk in enumerate(_chunks(input_list, size)):
        predicted_matches.extend(model.predict(input_chunk))
        if verbose:
            print("Finished with chunk nr.", chunk_index, ".")
    return predicted_matches


def get_matches_with_rules(df_matches: pd.DataFrame, df_rules: pd.DataFrame) -> pd.DataFrame:
    """
    Needs that df_matches index are 0 to df_matches.shape[0]
    """
    list_df_matches_by_rule = []
    for rule in df_rules.itertuples():
        df_matches_by_rule = df_matches.loc[rule.matchIndex]
        df_matches_by_rule["inputPattern"] = rule.inputPattern
        df_matches_by_rule["predictPattern"] = rule.predictPattern
        df_matches_by_rule["numMatches"] = rule.numMatches
        df_matches_by_rule["avgScore"] = rule.avgScore
        list_df_matches_by_rule.append(df_matches_by_rule)

    return pd.concat(list_df_matches_by_rule)
