/**
 * The mirror of `ValidationContext`.
 *
 * Checks run in order, each one recording what it found, so a later check can
 * read it -- the same contract the Python chain gives its validators.
 */

export interface Outcome {
  validator: string
  valid: boolean
  data: Record<string, unknown>
}

export interface PredicateDocument {
  value: unknown
  answers: Record<string, unknown>
  extra: Record<string, unknown>
  results: Record<string, { valid: boolean; data: Record<string, unknown> }>
}

export class ValidationContext {
  readonly answers: Record<string, unknown>
  readonly extra: Record<string, unknown>
  readonly outcomes: Outcome[] = []

  constructor(answers: Record<string, unknown> = {}, extra: Record<string, unknown> = {}) {
    this.answers = answers
    this.extra = extra
  }

  record(outcome: Outcome): void {
    this.outcomes.push(outcome)
  }

  outcomeFor(validator: string): Outcome | undefined {
    for (let index = this.outcomes.length - 1; index >= 0; index -= 1) {
      const outcome = this.outcomes[index]
      if (outcome && outcome.validator === validator) return outcome
    }
    return undefined
  }

  dataFor(validator: string): Record<string, unknown> {
    return this.outcomeFor(validator)?.data ?? {}
  }

  /** What a JMESPath predicate is evaluated against, field for field as in Python. */
  toDocument(value: unknown): PredicateDocument {
    const results: PredicateDocument["results"] = {}
    for (const outcome of this.outcomes) {
      results[outcome.validator] = { valid: outcome.valid, data: outcome.data }
    }
    return { value, answers: this.answers, extra: this.extra, results }
  }
}
