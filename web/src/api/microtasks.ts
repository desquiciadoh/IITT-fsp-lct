import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { customFetch } from '@/api/client'
import { keys } from '@/api/keys'
import type {
  Grade,
  MicroTask,
  MicroTaskDropCandidate,
  MicroTaskFormat,
  MicroTaskPrefill,
  MicroTaskSubmission,
  Spec,
} from '@/api/types'

// --- Employer: micro-task CRUD (BE-18) ------------------------------------------

/** POST /api/micro-tasks body. `key` is the server-side grading secret. */
export type CreateMicroTaskInput = {
  title: string
  specialization: Spec
  grades: Grade[]
  format: MicroTaskFormat
  prompt_md: string
  key?: unknown
  deadline?: string | null
}

export function useMicroTasks() {
  return useQuery({
    queryKey: keys.microTasks,
    queryFn: () => customFetch<MicroTask[]>('/api/micro-tasks'),
  })
}

export function useMicroTask(id: string) {
  return useQuery({
    queryKey: keys.microTask(id),
    queryFn: () => customFetch<MicroTask>(`/api/micro-tasks/${id}`),
    enabled: Boolean(id),
  })
}

export function useCreateMicroTask() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateMicroTaskInput) =>
      customFetch<MicroTask>('/api/micro-tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.microTasks }),
  })
}

export function useDeleteMicroTask() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      customFetch<void>(`/api/micro-tasks/${id}`, { method: 'DELETE' }),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.microTasks }),
  })
}

// --- Candidate: assigned drops and submissions (BE-18) ---------------------------

export function useMyMicroTasks() {
  return useQuery({
    queryKey: keys.myMicroTasks,
    queryFn: () => customFetch<MicroTaskDropCandidate[]>('/api/candidates/me/micro-tasks'),
  })
}

export function useSubmitMicroTask(dropId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (answer: unknown) =>
      customFetch<MicroTaskDropCandidate>(`/api/candidates/me/micro-tasks/${dropId}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer }),
      }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.myMicroTasks, exact: true })
    },
  })
}

// --- Employer: submissions review + invite (BE-18) --------------------------------

export function useMicroTaskSubmissions(taskId: string) {
  return useQuery({
    queryKey: keys.microTaskSubmissions(taskId),
    queryFn: () => customFetch<MicroTaskSubmission[]>(`/api/micro-tasks/${taskId}/submissions`),
    enabled: Boolean(taskId),
  })
}

export function useRateSubmission() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ dropId, employer_rating }: { dropId: string; employer_rating: number }) =>
      customFetch<MicroTaskSubmission>(`/api/micro-tasks/submissions/${dropId}/rate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employer_rating }),
      }),
    onSuccess: () => {
      // v5 cache: invalidate all submission queries under the base prefix.
      void client.invalidateQueries({ queryKey: ['micro-tasks'] })
    },
  })
}

/** POST prefill-offer → a Draft Offer form preloaded from the micro-task submission. */
export function usePrefillOffer() {
  return useMutation({
    mutationFn: (dropId: string) =>
      customFetch<MicroTaskPrefill>(`/api/micro-tasks/submissions/${dropId}/prefill-offer`, {
        method: 'POST',
      }),
  })
}