import argparse
import json

from pathlib import Path


def get_inputs():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "trace", type=str, help="Path to spatter trace to validate."
    )

    args = parser.parse_args()
    return Path(args.trace)


if __name__ == "__main__":
    trace = get_inputs()
    with trace.open() as spatter_trace:
        kernels = json.load(spatter_trace)
        for kernel in kernels:
            pattern = kernel["pattern"]
            if len(set(pattern)) != len(pattern):
                print("Oh no.")
            print(min(pattern), max(pattern))
