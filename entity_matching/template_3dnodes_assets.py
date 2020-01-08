# %%
%load_ext autoreload
%autoreload 2

# %%
import os
import json

import numpy as np
import pandas as pd
from cognite.client import CogniteClient

from cognite.client.data_classes.three_d import ThreeDAssetMapping

from cognite.datastudio.entity_matcher import EntityMatcher

# %%
# we provide functions to simplify the logics of the notebook
from utils import chunk_create_rules_df, chunk_predict, get_matches_with_rules

# we provide functions to install 3d-nodes, assets and asset-mappings
from data_load_cdf import load_assets, load_threednodes, filter_df_threednodes, load_asset_mappings

# %%
project = "akerbp"
api_key_name = "AKERBP_API_KEY"

# %%
# In case you need to add api-key
#from add_client_api_key import ClientApiKeyWidget
#client_api_key_widget = ClientApiKeyWidget(api_key_name=api_key_name, project=project)

# %%
client = CogniteClient(os.environ[api_key_name], project, "local-jupyter-notebook")

# %%
# define 3d model_id and revision
model_id = 1078941578276888
revision_id = 506407845865623

# define root_id for assets
root_id = 8129784932439587

#define a name to store thre predicted result
entity_matcher_results_file = "enma_skarv_fpso.json"

# %%
# download 3d nodes, it might take time
df_threednodes = load_threednodes(client, model_id, revision_id)
# filter the names of the 3d nodes that do not need contexualization
df_threednodes = filter_df_threednodes(df_threednodes, key_words=("EQUIPMENT", "BRANCH", "STRUCTURE", " of "))
df_threednodes.rename(columns={"name": "left_side_name"}, inplace=True)

# %%
# download assets
df_assets = load_assets(client, root_id).rename(columns={"name": "right_side_name"})

# %%
#download existing asset mappings from the 3d model
df_asset_mappings = load_asset_mappings(client, model_id, revision_id)

# %%
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

# %%
#initialize the entity matcher
entity_matcher = EntityMatcher(client)

# %%
# create rules form the existing mappings if exist
df_matches = \
    df_existing_matches[["left_side_name", "right_side_name"]]\
    .dropna()\
    .rename(columns = {"left_side_name": "input", "right_side_name": "predicted"})
df_matches["score"] = 1.0

pd_rules_from_existing = chunk_create_rules_df(entity_matcher, df_matches.to_dict('records'), size=100000)

# %%
# make predictions 
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

# %%
# predicted_matches filter on NAs, 
# NEEDreset index to match order before creating rules
df_predicted_matches = pd.DataFrame.from_dict(predicted_matches).dropna().reset_index(drop=True)

# %%
# create rules for predicted matches
pd_rules_from_predicted = chunk_create_rules_df(entity_matcher, df_predicted_matches.to_dict('records'), size=100000)

# %%
# associate matches with rules
df_predicted_with_rules = get_matches_with_rules(df_predicted_matches, pd_rules_from_predicted)

# %%
# assosicate predicted results with IDs
df_predicted_results_raw = df_predicted_with_rules\
    .merge(df_assets, left_on="predicted", right_on="right_side_name", how="inner")\
    .drop(columns=["right_side_name"])\
    .rename(columns={"id":"asset_id"})\
    .merge(df_threednodes, left_on="input", right_on="left_side_name", how="inner")\
    .drop(columns=["left_side_name"])\
    .rename(columns={"id":"node_id"})
df_predicted_results_raw.sample(5)

# %%
# comment or uncomment for different filtering
df_predicted_results = df_predicted_results_raw.copy()

# filter on the score value 
df_predicted_result = df_predicted_result[df_predicted_result["score"] > 0.0]

# filter on the avgScore value
df_predicted_result = df_predicted_result[df_predicted_result["avgScore"] > 0.0]

# filter by the number of matcher per rule
df_predicted_result = df_predicted_result[df_predicted_result["numMatches"] > 0]

# filter by merging on existing rules only
df_predicted_result = df_predicted_result.merge(pd_rules_from_existing\
    .rename(columns={"numMatches": "numMatchesExisting"})
    .drop(columns=["avgScore","matchIndex"]), on=["inputPattern", "predictPattern"],
    how="inner")

# filter out input with existing asset mappings
df_predicted_result = df_predicted_result\
    .merge(df_existing_matches.rename(columns={"right_side_name": "existing_match"}), left_on=["input"], right_on=["left_side_name"], how="left")\
    .drop(columns=["left_side_name"])
df_predicted_result= df_predicted_result[df_predicted_result["existing_match"].isna()]

# filter based on a list of manual rules
"""
rules_from_list = [("/[D1]-[L2]-[D3]", "[D1]-[L2]-[D3]")]
def get_rule_tuple(row):
    return (row["inputPattern"], row["predictPattern"])

df_predicted_result = df_predicted_result[df_predicted_result.apply(get_rule_tuple, axis=1)\
    .isin(rules_from_list)]
"""

df_predicted_result.sample(5)

# %%
# Create list of dictionaries to create ThreeDAssetMapping
resulting_asset_mappings =list(df_predicted_result[["node_id","asset_id"]].T.to_dict().values())
print(len(resulting_asset_mappings))
resulting_asset_mappings

# %%
# Create ThreeDAssetMappings
cdf_asset_mappings = []
for asset_mapping_dict in resulting_asset_mappings:
    cdf_asset_mappings.append(ThreeDAssetMapping(**asset_mapping_dict))

# %%
# Uncomment to write to clean:
#client.three_d.asset_mappings.create(model_id, revision_id, cdf_asset_mappings)

# %%


# %%
