# Maps a sample-pipeline scenario name (from the log's own "Scenario: <name>"
# line) to the FailureCategory it should have been classified as. Extend this
# alongside sample-pipeline whenever a new scenario is added -- if a scenario
# isn't listed here, eval skips it rather than guessing.
GROUND_TRUTH = {
    "schema_drift": "schema_drift",
    "data_quality": "data_quality",
    "data_quality_malformed": "data_quality",
    "timeout": "infra_timeout",
    "code_bug": "code_bug",
}
