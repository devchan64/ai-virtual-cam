def clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))
