import argparse
from promptbase.gsm8k import gsm8k
from promptbase.humaneval import humaneval
from promptbase.math import math
from promptbase.drop import drop
from promptbase.bigbench import bigbench
from promptbase.bigbench.consts import BIGBENCH_SUBJECTS

import promptbase.mmlu as mmlu


VALID_DATASETS = ["gsm8k", "humaneval", "math", "drop", "bigbench", "mmlu"]


def parse_arguments():
    p = argparse.ArgumentParser()
    p.add_argument(
        "dataset", type=str, choices=VALID_DATASETS, help="Name of dataset to test"
    )
    p.add_argument("--subject", type=str, help="Specify the subject for the dataset")
    p.add_argument(
        "--list_subjects",
        action="store_true",
        help="Lists the subjects available for the dataset",
    )
    return p.parse_args()


def main():
    args = parse_arguments()

    if args.list_subjects:
        if args.dataset == "bigbench":
            print(BIGBENCH_SUBJECTS)
        elif args.dataset == "mmlu":
            pass
        else:
            print(f"Dataset {args.dataset} does not have subjects")
        return

    if args.dataset == "gsm8k":
        gsm8k.generate()
        gsm8k.evaluate()
    elif args.dataset == "humaneval":
        humaneval.generate()
        humaneval.evaluate()
    elif args.dataset == "math":
        math.generate()
        math.evaluate()
    elif args.dataset == "drop":
        drop.generate()
        drop.evaluate()
    elif args.dataset == "bigbench":
        subject = args.subject if args.subject else "all"
        bigbench.generate(subject)
        bigbench.evaluate()
    elif args.dataset == "mmlu":
        # Note that to run the MMLU tests, you will need to download the
        # data, and then use the 'format_mmlu.py' script
        mmlu.generate(args.subject)
        pass
    else:
        raise ValueError(f"Bad dataset: {args.dataset}")


if __name__ == "__main__":
    main()
