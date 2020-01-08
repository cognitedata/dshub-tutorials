# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.3.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %load_ext autoreload
# %autoreload 2

# +
import os
import json

import numpy as np
import pandas as pd
from cognite.client import CogniteClient

from cognite.client.data_classes.three_d import ThreeDAssetMapping

from cognite.datastudio.entity_matcher import EntityMatcher

# +
# we provide functions to simplify the logics of the notebook
from utils import chunk_create_rules_df, chunk_predict, get_matches_with_rules

# we provide functions to install 3d-nodes, assets and asset-mappings
from data_load_cdf import load_assets, load_threednodes, filter_df_threednodes, load_asset_mappings
# -

# # Initialize

project = "akerbp"
api_key_name = "AKERBP_API_KEY"

from getpass import getpass
api_key = getpass()

client = CogniteClient(api_key, project, "local-jupyter-notebook")

# +
# define 3d model_id and revision
model_id = 1078941578276888
revision_id = 506407845865623

# define root_id for assets
root_id = 8129784932439587

#define a name to store thre predicted result
entity_matcher_results_file = "enma_skarv_fpso.json"
# -

# # Get the data

# download 3d nodes, it might take time
df_threednodes = load_threednodes(client, model_id, revision_id)
# filter the names of the 3d nodes that do not need contexualization
df_threednodes = filter_df_threednodes(df_threednodes, key_words=("EQUIPMENT", "BRANCH", "STRUCTURE", " of "))
df_threednodes.rename(columns={"name": "left_side_name"}, inplace=True)

# download assets
df_assets = load_assets(client, root_id).rename(columns={"name": "right_side_name"})

#download existing asset mappings from the 3d model
df_asset_mappings = load_asset_mappings(client, model_id, revision_id)

# Since df_asset_mappings includes only IDs,
# in order to get the names we join on the 
# df_assets, df_threednodes including available respective IDs and names.
df_existing_matches = (
        df_asset_mappings[["nodeId", "assetId"]]
        .merge(
            df_assets[["id", "right_side_name"]],
            how="left",
            left_on="assetId",
            right_on="id",
        )
        .drop(columns="id")
        .merge(
            df_threednodes[["id", "left_side_name"]],
            how="left",
            left_on="nodeId",
            right_on="id",
        )[["left_side_name", "right_side_name"]]
    )

# # Entity Matching with rules steps

#initialize the entity matcher
entity_matcher = EntityMatcher(client)

# +
# create rules form the existing mappings if exist
df_matches = \
    df_existing_matches[["left_side_name", "right_side_name"]]\
    .dropna()\
    .rename(columns = {"left_side_name": "input", "right_side_name": "predicted"})
df_matches["score"] = 1.0

pd_rules_from_existing = chunk_create_rules_df(entity_matcher, df_matches.to_dict('records'), size=100000)
# -

# Make predictions 
if os.path.exists(entity_matcher_results_file):
    print("Loading predicted from local...")
    with open(entity_matcher_results_file, "r") as f:
        predicted_matches = json.load(f)
else:
    model = entity_matcher.fit(df_assets["right_side_name"].tolist())
    predicted_matches = chunk_predict(model, df_threednodes["left_side_name"].tolist(), 100000)
    # store all predictions in a file
    with open(entity_matcher_results_file, "w") as f:
        json.dump(predicted_matches, f)

# We filter predicted_matches on NA-s
# We also need to reset index to match order before creating rules
df_predicted_matches = pd.DataFrame.from_dict(predicted_matches).dropna().reset_index(drop=True)

# Create rules for predicted matches
pd_rules_from_predicted = chunk_create_rules_df(entity_matcher, df_predicted_matches.to_dict('records'), size=100000)

# Associate matches with rules
df_predicted_with_rules = get_matches_with_rules(df_predicted_matches, pd_rules_from_predicted)

# Assosicate predicted results with IDs
df_predicted_results_raw = df_predicted_with_rules\
    .merge(df_assets, left_on="predicted", right_on="right_side_name", how="inner")\
    .drop(columns=["right_side_name"])\
    .rename(columns={"id":"asset_id"})\
    .merge(df_threednodes, left_on="input", right_on="left_side_name", how="inner")\
    .drop(columns=["left_side_name"])\
    .rename(columns={"id":"node_id"})
df_predicted_results_raw.sample(5)

# # Modify the filtering of the results

# +
df_predicted_results = df_predicted_results_raw.copy()

# comment or uncomment for different filtering

# ---
# filter on the score value 
df_predicted_results = df_predicted_results[df_predicted_results["score"] > 0.0]

# ---
# filter on the avgScore value
df_predicted_results = df_predicted_results[df_predicted_results["avgScore"] > 0.0]

# ---
# filter by the number of matcher per rule
df_predicted_results = df_predicted_results[df_predicted_results["numMatches"] > 0]

# ---
# filter by merging on existing rules only
df_predicted_results = df_predicted_results.merge(pd_rules_from_existing\
    .rename(columns={"numMatches": "numMatchesExisting"})
    .drop(columns=["avgScore","matchIndex"]), on=["inputPattern", "predictPattern"],
    how="inner")

# ---
# filter out the input 3d-nodes with existing asset mappings 
# or the predicted assets associated already to a 3d node via an asset mappings
df_predicted_results = df_predicted_results\
    .merge(df_existing_matches.rename(columns={"right_side_name": "existing_matching_asset"}), 
           left_on=["input"], 
           right_on=["left_side_name"], 
           how="left")\
    .drop(columns=["left_side_name"])

# filter out matching to the assets associated already to a 3d node via an asset mappings
df_predicted_results = df_predicted_results\
    .merge(df_existing_matches.rename(columns={"left_side_name": "existing_matching_3dnode"}), 
           left_on=["predicted"], 
           right_on=["right_side_name"], 
           how="left")\
    .drop(columns=["right_side_name"])

#keep this one if you want to investate the results
df_predicted_results_existing_input_3dnode = \
    df_predicted_results[~(df_predicted_results["existing_matching_asset"].isna())]
#keep this one if you want to investate the results
df_predicted_results_existing_predicted_asset = \
    df_predicted_results[~(df_predicted_results["existing_matching_3dnode"].isna())]

df_predicted_results = df_predicted_results[df_predicted_results["existing_matching_asset"].isna()]
df_predicted_results = df_predicted_results[df_predicted_results["existing_matching_3dnode"].isna()]

# ---
# filter based on a list of manual rules
"""
rules_from_list = [("/[D1]-[L2]-[D3]", "[D1]-[L2]-[D3]")]
def get_rule_tuple(row):
    return (row["inputPattern"], row["predictPattern"])

df_predicted_result = df_predicted_result[df_predicted_result.apply(get_rule_tuple, axis=1)\
    .isin(rules_from_list)]
"""

df_predicted_results.sample(5)
# -

# investigate what rows where thrown away because the input 3d node is already matched
df_predicted_results_existing_input_3dnode.sample(5)

# investigate what rows where thrown away because the asset is already mapped to some 3d node
df_predicted_results_existing_predicted_asset.sample(5)

# +
# count and print rows with several 3d nodes pointing to the same asset
df_predicted_count_assets = df_predicted_results.groupby("asset_id", as_index=False)["input"]\
    .count()\
    .rename(columns={"input":"count_assets"})

df_predicted_results\
    .merge(df_predicted_count_assets[df_predicted_count_assets["count_assets"]>1], on="asset_id", how="inner")\
    .sort_values("predicted")
# -

# Drop (for now as a solution) the mappings with several 3d nodes to the same asset 
df_predicted_results_unique = df_predicted_results\
    .merge(df_predicted_count_assets[df_predicted_count_assets["count_assets"]== 1], on="asset_id", how="inner")

# Create list of dictionaries to create ThreeDAssetMapping
resulting_asset_mappings =list(df_predicted_results_unique[["node_id","asset_id"]].T.to_dict().values())
print(len(resulting_asset_mappings))
resulting_asset_mappings

# Create ThreeDAssetMappings
cdf_asset_mappings = []
for asset_mapping_dict in resulting_asset_mappings:
    cdf_asset_mappings.append(ThreeDAssetMapping(**asset_mapping_dict))

# +
# Uncomment to write to clean:
#client.three_d.asset_mappings.create(model_id, revision_id, cdf_asset_mappings)
# -




