# Perplexity – Internship, Search Machine Learning Engineer (London)

The posting text I could read lists no form questions (the live page is JavaScript-rendered). Drafts for the usual ones below.

## Why Perplexity
Perplexity's product is search plus answer generation, so retrieval and ranking quality directly decide whether the answer is right. I want my first applied ML role to be on a system where model evaluation has a visible effect on users, and where LLM-based approaches are used for ranking and judging rather than only for chat.

## What aspects of Perplexity are you most excited to work on? (form question)
Draft (about 140 words):

> The part of Perplexity I find most interesting is that the answer is only as good as the retrieval and ranking underneath it, and that quality is measurable. Every answer cites its sources, so a bad ranking shows up immediately as a wrong or unsupported claim. That makes search ML at Perplexity a tight loop: improve retrieval or ranking, then check whether the final answer got more accurate and better grounded.
>
> I am especially excited about using LLMs to evaluate that loop. At the Max Planck Institute I built a dataset labelled by a 31B LLM judge (95% of labels validated) and used it to fine-tune Qwen2.5-3B over five versions. I would like to apply the same approach to ranking and answer quality at a much larger scale, on a product people use every day.

Shorter version (about 60 words), if the box is small:

> Retrieval and ranking decide whether a cited answer is right, so search quality is directly measurable. I'm most excited to work on LLM-based evaluation of that quality. At the Max Planck Institute I built an LLM-judged dataset (95% validated) and fine-tuned Qwen2.5-3B over five versions. I'd like to apply that loop to ranking at Perplexity's scale.

Notes:
- Everything about Perplexity here comes from the posting (retrieval, ranking, RAG, LLM-based evaluation) plus the well-known fact that answers cite sources. I did not add claims about internal systems.
- [ASK FARES: if there is a specific Perplexity product or blog post you actually find interesting (Sonar API, Deep Research, Comet), name it in one sentence. A concrete detail you chose yourself reads better than a general one.]

## Why this role
It asks for ML and statistics foundations, Python with PyTorch, and work on retrieval, ranking, RAG and LLM-based evaluation models. At the Max Planck Institute I built a dataset, used a 31B LLM as a judge (95% of labels validated) and fine-tuned Qwen2.5-3B over five versions. That is the same loop of data, training and evaluation.

## A project I'm proud of
Max Planck mode-collapse project: I asked whether an LLM can detect when a closed-loop conversation has become repetitive, and recover. 8,504 examples from 10,000 self-conversations, labelled by a 31B LLM judge (95% validated), full fine-tune of Qwen2.5-3B over five versions on SLURM with vLLM. The model detects its own collapse in unseen conversations; recovery was only temporary, which I reported as such. [ASK FARES: add the headline detection number if you have it, see cv_feedback Q1]

## Experience with search, ranking or recommender systems
[ASK FARES: the posting wants coursework or projects in information retrieval, ranking or recommenders. Your CV has none named. Do you have any (a UCL module project, a reranker, an embedding search)? If not, answer honestly: "No dedicated IR project yet; closest is my RAG-adjacent agent work and LLM-judge evaluation."]

## Right to work / sponsorship
I am a French citizen. I am currently in the UK on a student visa while I study at UCL. [ASK FARES: confirm wording. The profile says the UK needs sponsorship or the Graduate visa. For an internship during your MSc, say whether you can work full-time in the dates they offer. Student-visa work is capped at 20h/week in term time, with full-time only in official vacations.]

## Start date / duration
The posting says 12–24 weeks, full-time, in person in London, with no dates stated. I graduate from UCL in September 2027. [ASK FARES: what dates can you actually do? Term time caps you at 20h/week, and your profile excludes summer 2027 because of the dissertation. Say which window you are offering, e.g. a vacation block.]

## Salary expectations
[ASK FARES: the posting states no pay. Give a figure or say "in line with your standard internship rate".]

## Rust
Not on my CV. If asked: I have not used Rust professionally; I work in Python, C, C++ and Java and would learn it on the job. [ASK FARES: true? Adjust if you have used Rust.]
