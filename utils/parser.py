def parse_ai_response(response: str) -> dict:
    lines = response.strip().split("\n")
    data = {}

    for line in lines:
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip()

    return data
