def handle(client, data):
    # When deploying a function from a notebook like this, all imports must be performed inside the `handle` function.
    from cognite.experimental import CogniteClient
    from cognite.client.data_classes import TimeSeriesUpdate
    import time
    
    # The entity matcher suggests matches with a certain score. To achieve a reasonable result, this score must be adjusted. 
    # The default value of 0.75 has been chosen by inspecting the outcome of this function, and may be different on data from other customers.
    good_match_threshold = data.get("good_match_threshold", 0.75)
    
    # Create experimental SDK client as the contextualization API's are in playground and are thus not available in the regular SDK.
    client = CogniteClient(api_key = client.config.api_key, base_url = client.config.base_url, project = client.config.project)

    # Download all assets and time series, using 5 requests in parallel
    assets = client.assets.list(limit=-1, partitions=5)
    time_series = client.time_series.list(limit=-1, partitions=5)
    
    # Create simplified objects with only name and id
    assets_simplified = [{"id": asset.id, "name": asset.name} for asset in assets]
    time_series_simplified = [{"id": ts.id, "name": ts.name} for ts in time_series]

    # Train the ML Entity Matcher on the data. The SDK expects as input the array of objects you match FROM (time series) and a list of what you match TO (assets)
    t0 = time.time()
    model = client.entity_matching.fit(sources = time_series_simplified, targets = assets_simplified)
    print(f"Training entity matcher model with id {model} ...")
    model.wait_for_completion()
    t1 = time.time()
    print(f"Model {model} trained on {len(assets_simplified)} assets and {len(time_series_simplified)} time series using {t1-t0} seconds")

    # Use the ML Entity Matcher model to match the data. This model can be reused, so training is not necessary each time, but we do it for simplicity in this example.
    t0 = time.time()
    job = model.predict(time_series_simplified)
    result = job.result # This will wait for completion
    t1 = time.time()
    print(f"Predict finished after {t1-t0} seconds on {len(time_series_simplified)} time series.")
    
    # Filter out the best matches with the threshold specified in the input
    good_match_count = 0
    time_series_updates = []
    for item in result["items"]:
        match_from = item["source"] # Time series
        matches = item["matches"] # Suggested asset matches for the time series
        good_matches = [match for match in matches if match["score"] >= good_match_threshold]
        if len(good_matches) > 0:
            good_match_count += 1
            best_match = good_matches[0]
            time_series_updates.append(TimeSeriesUpdate(id=match_from["id"]).asset_id.set(best_match["target"]["id"]))
    
    client.time_series.update(time_series_updates) # uncomment to actually update the asset_id field
    print(f"Matched {good_match_count} time series to assets")
    return {
        "matches": good_match_count
    }
