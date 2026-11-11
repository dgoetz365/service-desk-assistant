# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python 3.12 standard library with static HTML, CSS, and JavaScript, as requested. No package installation is needed.

## Users

Assumption for this demonstration: a bicycle repair shop associate preparing an answer to a customer's service question.

## Product Purpose

Look up synthetic repair records and policy, display the evidence, and prepare a response for human review.

## Capabilities and Constraints

- A deterministic offline router is explicitly labeled as a demo; an optional local Ollama adapter uses model tool calls.
- Read-only, allowlisted repair, part, and policy tools. There is no sending or business-record writing capability.
- Unknown and ambiguous requests must remain visible; unavailable dates and costs must not be guessed.
- Localhost only. No external assets, account credentials, real customers, or production systems.
- No browser use or screenshot verification was authorized for this build.

## Evidence on Hand

All fixtures are invented for this repository. No real operational records or personal information are included. Automated tests can establish protocol and boundary behavior; they cannot establish real model quality or rendered visual quality.

## Product Principles

1. Evidence appears before a response draft.
2. A draft is always a draft, even when it sounds confident.
3. Unknown information stays unknown.
4. Tool authority is enforced in code, independently of prompts.

## Accessibility & Inclusion

Native controls, visible focus, text labels, responsive layout, and status announcements. Manual keyboard and screen-reader verification remains pending.
