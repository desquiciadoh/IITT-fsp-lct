import { useEffect, useRef } from 'react'

/**
 * FE-05 · integrity metadata capture (BE.md §H5).
 *
 * Silently counts, per item:
 *  - `focus_loss` — tab switches (`visibilitychange` → hidden);
 *  - `paste`      — clipboard pastes inside the answer area.
 *
 * The counters ride along with the answer payload; the candidate never sees
 * any warning or badge about them (neutral UX is a product requirement).
 */

/** Wire shape (BE.md H5): snake_case keys go straight onto the answer body. */
export type IntegrityCounters = { focus_loss: number; paste: number }

const ZERO: IntegrityCounters = { focus_loss: 0, paste: 0 }

/**
 * Ref-based counter reset whenever the served item changes (new `item_id`).
 * Returns a getter to be read at submit time — not reactive on purpose.
 */
export function useIntegrity(itemId: string | undefined) {
  const counters = useRef<IntegrityCounters>({ ...ZERO })

  // New item → fresh counters (deadline and integrity are per item).
  useEffect(() => {
    counters.current = { ...ZERO }
  }, [itemId])

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') counters.current.focus_loss += 1
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  const bumpPaste = () => {
    counters.current.paste += 1
  }

  const read = (): IntegrityCounters => ({ ...counters.current })

  return { counters, read, bumpPaste }
}

/** Normalize captured counters into the wire shape (`AnswerIntegrity`). */
export function toWireIntegrity(c: IntegrityCounters): IntegrityCounters {
  return { focus_loss: c.focus_loss, paste: c.paste }
}
