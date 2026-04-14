import argparse
import random


def generate_inputs(num_elements, seed):
    random.seed(seed)

    # Generate index as a random permutation of 0..n-1
    index = list(range(num_elements))
    random.shuffle(index)

    # Generate n random float values for data
    data = [round(random.uniform(1.0, 10.0), 2) for _ in range(num_elements)]

    # Write index.txt
    with open("index.txt", "w") as index_file:
        for i in index:
            index_file.write(f"{i}\n")

    # Write data.txt
    with open("data.txt", "w") as data_file:
        for val in data:
            data_file.write(f"{val}\n")

    with open("info", "w") as info_file:
        info_file.write(f"num_elements: {num_elements}\n")
        info_file.write(f"seed: {seed}\n")

    print(f"✅ Wrote data.txt and index.txt with {num_elements} entries each")


# Example usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate test inputs for MPI benchmark"
    )
    parser.add_argument(
        "num_elements", type=int, help="Number of entries to generate"
    )
    parser.add_argument(
        "seed", type=int, help="Random seed for reproducibility"
    )
    args = parser.parse_args()

    generate_inputs(args.num_elements, args.seed)
