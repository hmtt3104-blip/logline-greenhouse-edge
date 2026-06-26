# Firebase command sync

## Problem

App-side command intent needs a controlled boundary before it reaches local devices.

## Hypothesis

A pending/history queue model can separate command intent, processing, and result tracking.

## Experiment

Keep Firebase-style paths generic and document the processing lifecycle without private project details.

## Status

Draft from sanitized export.

## Trust level

Low-Medium. The public export needs mocked or documented replay before confidence increases.

## Next question

Should the public version include a local fake sync backend for testing?
