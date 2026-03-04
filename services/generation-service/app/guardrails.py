def is_prompt_attack_query(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        "ignore previous instructions",
        "ignore all previous instructions",
        "reveal system prompt",
        "show system prompt",
        "print system prompt",
        "developer message",
        "hidden prompt",
        "jailbreak",
        "override your instructions",
    ]
    return any(pattern in lowered for pattern in patterns)
