"""
main.py
Run this once loader.py (the organizers' file) is sitting in this same
folder. Usage:

    export ANTHROPIC_API_KEY=sk-...

    # against the static bundle / data_v2 folder:
    python3 main.py --data ../data_v2 --out submission.json

    # against the running docker server, and score immediately:
    python3 main.py --data http://localhost:8080 --out submission.json --submit

Either way, once you have submission.json you can also score it directly
with the organizers' CLI, without going through this script at all:

    python3 score_cli.py submission.json --ground-truth ../data_v2/ground_truth.json
"""

import argparse
import json

import anthropic
from dotenv import load_dotenv
from loader import Inbox  # the organizers' file -- copy it into this folder
from pipeline import ShippingVerificationPipeline

load_dotenv()  # reads .env if present in this folder; harmless if it's not


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="../data_v2",
                        help="Path to data_v2/, or the running server's URL")
    parser.add_argument("--out", default="submission.json")
    parser.add_argument("--submit", action="store_true",
                        help="POST results to the server's /submit (HTTP source only)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N emails (useful while iterating)")
    args = parser.parse_args()

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    inbox = Inbox(args.data)

    pipeline = ShippingVerificationPipeline(client, inbox)

    if args.limit:
        # Small-batch dev loop: monkey-patch the inbox iterator to the first
        # N emails so you're not burning API calls on all 520 while testing.
        original_emails = inbox.emails
        inbox.emails = lambda: original_emails()[: args.limit]

    results = pipeline.run()

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Wrote {len(results)} results to {args.out}")

    if args.submit:
        score = inbox.submit(results)
        print(json.dumps(score, indent=2))


if __name__ == "__main__":
    main()