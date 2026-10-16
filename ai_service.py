def ai_commit(diff, model, temperature, max_tokens, safe_mode=False):
    if safe_mode:
        diff = limit_diff(diff)
    prompt = ai_prompt(diff, "commit")
    response = ai_cal_api(prompt, model, temperature, max_tokens)
    return ai_validate(response, "commit")


def ai_pr(diff, model, temperature, max_tokens, safe_mode=False):
    if safe_mode:
        diff = limit_diff(diff)
    prompt = ai_prompt(diff, "pr")
    response = ai_cal_api(prompt, model, temperature, max_tokens)
    return ai_validate(response, "pr")


def ai_prompt(diff, str):
    return


def ai_validate(response, str):
    return

def ai_cal_api(prompt, model, temperature, max_tokens):
    return

def limit_diff(diff):
    return
