from pagerwise_api import prompts
from pagerwise_api.settings import settings


def test_judge_window_matches_the_deploy_window_triage_uses():
    # The judge's "shortly before" must mean the same window triage gathers deploys from.
    assert f"up to {settings.triage_deploy_window_h} hours before" in prompts.JUDGE_SYSTEM
