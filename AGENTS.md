# Agent Notes

## Engine Change Rule
- If any change is made in an engine implementation, run validation for that engine against only ONE configured target(data or bypass) before considering the change complete. if browser doesnt start fix it.
- Use `run_single_engine_check.py` for this validation run.

To run python and install libs use local venv: venv or .venv