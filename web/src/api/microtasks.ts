import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type { EmployerMicroTask, MicroTask, MicroTaskDrop } from '@/api/types'

/**
 * FE-16 micro-tasks (Gap G19 / BE-18): candidate inbox + solve, employer
 * create/review/invite — all mocked in `@/mocks/handlers/microtasks`.
 */

export function useMicroTasks() {
  return useQuery({
    queryKey: keys.microtasks,
    queryFn: () => customFetch<MicroTask[]>('/api/microtasks'),
  })
}

export function useMicroTask(id: string) {
  return useQuery({
    queryKey: keys.microtask(id),
    queryFn: () => customFetch<MicroTask>(`/api/microtasks/${id}`),
    enabled: Boolean(id),
  })
}

export function useMyDrops() {
  return useQuery({
    queryKey: keys.myDrops,
    queryFn: () => customFetch<MicroTaskDrop[]>('/api/microtasks/drops/me'),
  })
}

export function useSubmitMicroTask(taskId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (answer: unknown) =>
      customFetch<MicroTaskDrop>(`/api/microtasks/${taskId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['microtasks'] })
      void client.invalidateQueries({ queryKey: ['employer', 'microtasks'] })
    },
  })
}

export function useEmployerMicroTasks() {
  return useQuery({
    queryKey: keys.employerMicrotasks,
    queryFn: () => customFetch<EmployerMicroTask[]>('/api/employer/microtasks'),
  })
}

export function useCreateMicroTask() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      title: string
      specialization: string
      grades: string[]
      format: 'auto' | 'open'
      prompt_md: string
      deadline: string
    }) =>
      customFetch<MicroTask>('/api/employer/microtasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['employer', 'microtasks'] })
    },
  })
}

export function useReviewDrop() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, rating, shared }: { id: string; rating: number; shared: boolean }) =>
      customFetch<MicroTaskDrop>(`/api/microtasks/drops/${id}/review`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employer_rating: rating, shared }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['employer', 'microtasks'] })
      void client.invalidateQueries({ queryKey: ['microtasks'] })
    },
  })
}