# Chunk Hash Compare Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chunk hash compare isinin uygulanabilir sinirini netlestirip, gerekirse `diff log` ile birlikte ele almak.

**Architecture:** Mevcut schema child vector'i DB'de tutmadigi icin gercek embed skip/coherent carry-forward icin yalniz chunk hash yetmiyor. Bu nedenle bir sonraki anlamli implementasyon parcasini `chunk hash compare + diff log` birlikte ele almak gerekiyor.

**Tech Stack:** Ingestion service, repository, Qdrant bridge, pytest

---

## Chunk 1: Feasibility lock

### Task 1: Blocking constraint'i dokumante et

**Files:**
- This plan only

- [x] Step 1: Current schema/flow limitation'i acikla
- [x] Step 2: Next executable unit'i `diff log` ile birlestir

