import { useState } from 'react'
import type { KeyboardEvent } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Editable chips list (FE-09 position wizard: must/nice skills).
 * Enter or comma commits the pending text; Backspace on empty input
 * removes the last chip. `highlight` marks values coming from the JD
 * parser's `unknown_terms` so they stand out for review.
 */
export function ChipInput({
  value,
  onChange,
  placeholder,
  label,
  suggestions = [],
  highlight = [],
  id,
}: {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  label?: string
  suggestions?: string[]
  highlight?: string[]
  id?: string
}) {
  const [pending, setPending] = useState('')

  const commit = (raw: string) => {
    const skill = raw.trim().toLowerCase()
    if (!skill) return
    if (!value.includes(skill)) onChange([...value, skill])
    setPending('')
  }

  const remove = (skill: string) => onChange(value.filter((v) => v !== skill))

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      commit(e.currentTarget.value)
    } else if (e.key === 'Backspace' && e.currentTarget.value === '' && value.length > 0) {
      remove(value[value.length - 1])
    }
  }

  const openSuggestions = suggestions
    .map((s) => s.toLowerCase())
    .filter((s) => (pending ? s.includes(pending.trim().toLowerCase()) : !value.includes(s)))
    .slice(0, 6)

  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
      )}
      <div
        className={cn(
          'flex min-h-10 flex-wrap items-center gap-1.5 rounded-md border border-input bg-background p-1.5',
          'focus-within:ring-2 focus-within:ring-ring/50',
        )}
      >
        {value.map((skill) => (
          <span
            key={skill}
            className={cn(
              'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs',
              highlight.includes(skill)
                ? 'border-warn/50 bg-warn/10 text-warn'
                : 'border-border bg-muted text-foreground',
            )}
          >
            {skill}
            <button
              type="button"
              aria-label={`Удалить ${skill}`}
              onClick={() => remove(skill)}
              className="rounded-full p-0.5 hover:bg-foreground/10"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={pending}
          onChange={(e) => setPending(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => commit(pending)}
          placeholder={value.length === 0 ? placeholder : undefined}
          className="min-w-24 flex-1 bg-transparent px-1 text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      {openSuggestions.length > 0 && (
        <div className="flex flex-wrap gap-1" role="listbox" aria-label="Подсказки">
          {openSuggestions.map((s) => (
            <button
              key={s}
              type="button"
              role="option"
              aria-selected={false}
              onClick={() => commit(s)}
              className="rounded-full border border-dashed border-border px-2 py-0.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
