// API 请求封装 — 所有后端请求从这里发出

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

class ApiClientError extends Error {
  constructor(public status: number, public detail: string) {
    super(detail)
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiClientError(res.status, err.detail || 'Unknown error')
  }
  return res.json()
}

export type CollectionBookSummary = {
  book_id: string
  title: string | null
  author: string | null
  status: string
  page_count: number | null
  order_index: number
}

export type CollectionSummary = {
  id: string
  name: string
  description: string | null
  status: string
  book_count: number
  created_at: string
  updated_at: string
}

export type CollectionDetail = CollectionSummary & {
  books: CollectionBookSummary[]
}

export type CollectionSkill = {
  id: string
  collection_id: string
  skill_md: string | null
  scripts: Record<string, unknown> | null
  templates: Record<string, unknown> | null
  zip_path: string | null
  version: number
  status: string
  created_at: string
  updated_at: string
}

// ─── Books ───────────────────────────────────────────────────────────────────

export async function uploadBook(file: File) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/api/books/upload`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) throw new ApiClientError(res.status, 'Upload failed')
  return res.json() as Promise<{ book_id: string; message: string }>
}

export async function getBookStatus(bookId: string) {
  return request<{
    book_id: string; status: string; title: string | null;
    author: string | null; page_count: number | null; error_message: string | null; created_at: string
  }>(`/api/books/${bookId}/status`)
}

export async function listBooks() {
  return request<Array<{
    book_id: string; title: string | null; author: string | null;
    status: string; page_count: number | null; created_at: string;
    skill_id: string | null; skill_status: string | null;
  }>>(`/api/books`)
}

// ─── Collections ─────────────────────────────────────────────────────────────

export async function listCollections() {
  return request<CollectionSummary[]>(`/api/collections`)
}

export async function createCollection(input: {
  name: string
  description?: string | null
  book_ids: string[]
}) {
  return request<CollectionDetail>(`/api/collections`, {
    method: 'POST',
    body: JSON.stringify(input),
  })
}

export async function getCollection(collectionId: string) {
  return request<CollectionDetail>(`/api/collections/${collectionId}`)
}

export async function updateCollection(
  collectionId: string,
  input: { name?: string; description?: string | null; book_ids?: string[] }
) {
  return request<CollectionDetail>(`/api/collections/${collectionId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
}

export async function deleteCollection(collectionId: string) {
  return request<{ message: string }>(`/api/collections/${collectionId}`, {
    method: 'DELETE',
  })
}

// ─── Collection Skills ───────────────────────────────────────────────────────

export async function getCollectionSkill(skillId: string) {
  return request<CollectionSkill>(`/api/collection-skills/${skillId}`)
}

export async function packCollectionSkill(skillId: string) {
  return request<{ skill_package_id: string; zip_path: string; message: string }>(
    `/api/collection-skills/${skillId}/pack`,
    { method: 'POST' }
  )
}

export function getCollectionSkillDownloadUrl(skillId: string) {
  return `${API_BASE}/api/collection-skills/${skillId}/download`
}

// ─── Skills ──────────────────────────────────────────────────────────────────

export async function generateSkill(
  bookId: string,
  options?: { focus_chapters?: number[]; user_goal?: string }
) {
  return request<{ id: string; status: string }>(`/api/skills/books/${bookId}/generate`, {
    method: 'POST',
    body: JSON.stringify(options || {}),
  })
}

export async function getSkill(skillId: string) {
  return request<{
    id: string; book_id: string; skill_md: string | null;
    scripts: Record<string, unknown> | null;
    zip_path: string | null;
    status: string; version: number; created_at: string; updated_at: string
  }>(`/api/skills/${skillId}`)
}

export async function packSkill(skillId: string) {
  return request<{ skill_package_id: string; zip_path: string; message: string }>(
    `/api/skills/${skillId}/pack`,
    { method: 'POST' }
  )
}

export function getDownloadUrl(skillId: string) {
  return `${API_BASE}/api/skills/${skillId}/download`
}

// ─── Chat (SSE Streaming) ────────────────────────────────────────────────────

export async function* refineSkillStream(
  skillId: string,
  instruction: string
): AsyncGenerator<string> {
  const res = await fetch(`${API_BASE}/api/chat/skills/${skillId}/refine`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  })
  if (!res.ok || !res.body) throw new ApiClientError(res.status, 'Refine failed')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') return
        try {
          const obj = JSON.parse(data)
          yield obj.content
        } catch (e) {
          // If not JSON (like [DONE] or error), just yield as is or ignore
          yield data
        }
      }
    }
  }
}

export async function bookQA(bookId: string, question: string) {
  return request<{ answer: string; sources: Array<{ chapter: string; page: number | null; quote: string; score: number }> }>(
    `/api/chat/books/${bookId}/qa`,
    { method: 'POST', body: JSON.stringify({ question }) }
  )
}

export async function* playGroundStream(
  skillId: string,
  message: string,
  history: Array<{ role: string; content: string }> = []
): AsyncGenerator<string> {
  const res = await fetch(`${API_BASE}/api/chat/skills/${skillId}/playground`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })
  if (!res.ok || !res.body) throw new ApiClientError(res.status, 'Playground stream failed')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') return
        try {
          const obj = JSON.parse(data)
          yield obj.content
        } catch (e) {
          yield data
        }
      }
    }
  }
}
