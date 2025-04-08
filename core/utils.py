import uuid
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs


def append_random_params(original_url: str, num_params: int = 3) -> str:
    """Appends random parameters to an existing URL."""
    parsed_url = urlparse(original_url)
    raw_params = parse_qs(parsed_url.query)
    query_params = {key: values[0] for key, values in raw_params.items()}

    for _ in range(num_params):
        query_params[str(uuid.uuid4())] = str(uuid.uuid4())

    new_query_string = urlencode(query_params)
    return urlunparse(parsed_url._replace(query=new_query_string))


if __name__ == "__main__":
    # Example usage
    url = "https://example.com/search?faf=faf"
    print(append_random_params(url))

