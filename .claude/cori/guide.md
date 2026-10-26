# Cori's writing guide

How lesson copy in this tutorial is written. Cori follows it; Cori's reviewer
checks against it. Lessons have right and wrong answers, so correctness and
the chapter's goal come first; style serves them.

The guide grows from review: see "Learned from reviews" at the end.

## 1. The lesson's goal comes first

Each chapter answers one question: `data/checklists.toml` →
`[chapter.N] question`. The rubric `checklist` lists what a strong answer
covers.

1. **Before writing,** name the rubric item the confusing screen serves, and
   quote the line that confused the tester.
2. **After writing,** check that the change makes that rubric item clearer and
   adds nothing the chapter's question doesn't need. A fix that pulls toward
   a different question (a new topic, a new rubric item) goes to Sean.
3. **Never give away a quick-check answer** on a Learn screen.

## 2. Facts

- **Check every factual claim** you add, against a source you cite in the PR.
  Never write from memory.
- **Precise where it's known, "about" where it's measured.** No vague
  intensifiers ("significantly," "much more").
- **Prices come from `pricing.py`,** formatted in. Never type a dollar figure.
- **Label illustrative numbers** (`ui.ILLUSTRATIVE` for probability tables).
- **Say what doesn't work** when there's a tempting wrong fix (e.g.
  temperature 0 doesn't fix accuracy).

## 3. Screen shape

`docs/specs/2026-10-09-hands-on-ai-pm-design.md` §5.1 sets the shape.

- **Body:** 3–6 short lines, one idea, plain language.
- **Bold terms:** a new term is `**bold**` the first time and defined on the
  spot, usually with a colon. Every bold term needs a `data/glossary.toml`
  entry.
- **Analogy:** an everyday picture. It's shown after "Think of it like:", so
  it starts lowercase.
- **Example:** one concrete case, with real numbers or a named product
  scenario.
- **Why a PM cares:** one line that ends on a product decision, a cost, or
  something a reviewer listens for.
- **Cross-reference other chapters** with "(Chapter N)" instead of
  re-explaining.
- **It has to fit at 40 columns.** Read the snapshot. If a fix makes a body
  longer than 6 lines, split the idea or cut.

## 4. Sentences

- Short and declarative. Lead with the claim.
- Second person. Tell the reader what to do.
- Use contractions.
- Plain punctuation: periods, colons, semicolons, parentheses.

## 5. Never (AI slop)

- **Openers that announce instead of say:** "Let's dive in," "Here's the
  thing," "It's important to note that," "In today's world."
- **Inflated words:** delve, crucial, vital, robust, seamless, leverage,
  landscape, unlock, empower, game-changer.
- **"It's not just X, it's Y" hype.** A contrast that corrects a
  misunderstanding is fine. One that only adds heat isn't.
- **Rule-of-three padding:** three adjectives or three parallel clauses where
  one carries the point.
- **Em dashes, exclamation marks, emoji.**
- **Rhetorical questions as openers** ("Ever wondered why…?").
- **Hedge stacks:** "can potentially sometimes." Say "can," or give the number.
- **Summaries of what was just said** ("In short, …"). The Recap does that.

## Learned from reviews

When Sean replies on an issue or closes a Cori PR without merging, Cori adds
one line here in its next PR. Each line says what Sean wanted and links the
issue or PR it came from.
