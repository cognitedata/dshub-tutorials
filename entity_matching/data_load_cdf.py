import os
from typing import List, Tuple

import pandas as pd
from cognite.client import CogniteClient


def load_pd_csv_if_exists(filename: str):
    if filename and os.path.exists(filename):
        print("Loading data from local...")
        return pd.read_csv(filename, header=0)
    print(f"No file with filename '{filename}' found.")


def load_assets(client: CogniteClient, root_id: int) -> pd.DataFrame:
    """
    Load assets from CDF
    """
    filename = f"assets_from_root_id_{root_id}.csv"
    df_assets = load_pd_csv_if_exists(filename)
    if df_assets is not None:
        return df_assets
    print("Loading assets from CDF...")
    assets = client.assets.list(root_ids=[root_id], limit=-1)
    df_assets = assets.to_pandas()[["name", "id"]]
    df_assets.to_csv(filename, index=False)
    return df_assets


def load_threednodes(client: CogniteClient, model_id: int, revision_id: int) -> pd.DataFrame:
    """
    Load 3d-nodes from CDF`.
    """
    filename = f"threednodes_model_{model_id}_revision_{revision_id}.csv"
    df_threednodes = load_pd_csv_if_exists(filename)
    if df_threednodes is not None:
        return df_threednodes
    print("Loading 3D nodes from CDF...")
    threednodes = client.three_d.revisions.list_nodes(model_id=model_id, revision_id=revision_id, limit=-1)
    df_threednodes = threednodes.to_pandas()[["name", "id"]]
    df_threednodes.to_csv(filename, index=False)
    return df_threednodes


def filter_df_threednodes(
    df_threednodes: pd.DataFrame, key_words: List[str] = ("EQUIPMENT", "BRANCH", "STRUCTURE", " of ")
) -> pd.DataFrame:
    """
    Filter out pd.Dataframe based on keywords in ["name"]. Words in the key_words found in the names
    indicate that 3D nodes do not need contextualization.
    """
    print("Filtering 3D-nodes:")
    df_filtered_threednodes = df_threednodes.copy()
    print("%d initially loaded" % df_filtered_threednodes.shape[0])

    df_filtered_threednodes["name"] = df_filtered_threednodes["name"].astype(str)
    df_filtered_threednodes = df_filtered_threednodes[df_filtered_threednodes["name"] != ""]
    print("%d after filtering on empty name" % df_filtered_threednodes.shape[0])

    df_filtered_threednodes.drop_duplicates(subset=["name"], inplace=True, keep=False)
    print("%d after dropping duplicates" % df_filtered_threednodes.shape[0])

    for key_word in key_words:
        df_filtered_threednodes = df_filtered_threednodes[~df_filtered_threednodes["name"].str.contains(key_word)]
        print("{0} after filtering on {1}".format(df_filtered_threednodes.shape[0], key_word))
    return df_filtered_threednodes


def load_asset_mappings(client: CogniteClient, model_id: int, revision_id: int) -> pd.DataFrame:
    """
    Load asset_mappings for the 3D model
    """
    filename = f"threednodes_asset_mappings_model_{model_id}_revision_{revision_id}.csv"
    df_asset_mappings = load_pd_csv_if_exists(filename)
    if df_asset_mappings is not None:
        return df_asset_mappings
    print("Loading assets from CDF...")
    asset_mappings = client.three_d.asset_mappings.list(model_id=model_id, revision_id=revision_id, limit=-1)
    df_asset_mappings = asset_mappings.to_pandas()
    df_asset_mappings.to_csv(filename, index=False)
    return df_asset_mappings
