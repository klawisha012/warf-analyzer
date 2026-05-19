/**
 * WeaponPicker — populates a shadcn <Select> with the union of
 * `good_weapons` keys + `fast_weapons_list`, deduplicated and sorted.
 */
import { useQuery } from '@tanstack/react-query'

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { api } from '@/lib/api'
import type { Settings } from '@/types'

type Props = {
  value: string | null
  onChange: (weapon: string) => void
}

export function WeaponPicker({ value, onChange }: Props) {
  const query = useQuery({
    queryKey: ['weapons'],
    queryFn: () => api<Settings>('/api/weapons'),
  })

  const weapons: string[] = (() => {
    if (!query.data) return []
    const good = Object.keys(query.data.good_weapons ?? {})
    const fast = query.data.fast_weapons_list ?? []
    const all = new Set<string>([...good, ...fast])
    return Array.from(all).sort()
  })()

  return (
    <Select
      value={value ?? ''}
      onValueChange={(v) => {
        if (v) onChange(v)
      }}
    >
      <SelectTrigger className="bg-rs-panel-hi border-rs-border text-rs-text">
        <SelectValue placeholder={query.isPending ? 'Loading…' : 'Select weapon…'} />
      </SelectTrigger>
      <SelectContent className="max-h-[60vh]">
        {weapons.map((w) => (
          <SelectItem key={w} value={w}>
            {w}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
