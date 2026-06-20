'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { ArrowLeft, BookOpen, Layers, Loader2, Trash2 } from 'lucide-react'
import {
  CollectionDetail,
  CollectionSkillRun,
  deleteCollection,
  generateCollectionSkill,
  getCollection,
  listCollectionSkills,
  retryCollectionSkill,
} from '@/lib/api'
import { useI18n } from '@/lib/i18n'

export default function CollectionDetailPage() {
  const { t } = useI18n()
  const params = useParams()
  const router = useRouter()
  const collectionId = params.collectionId as string
  const [collection, setCollection] = useState<CollectionDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [userGoal, setUserGoal] = useState('')
  const [generating, setGenerating] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [runs, setRuns] = useState<CollectionSkillRun[]>([])
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null)

  useEffect(() => {
    if (!collectionId) return
    Promise.allSettled([getCollection(collectionId), listCollectionSkills(collectionId)])
      .then(results => {
        const collectionResult = results[0]
        const runsResult = results[1]
        if (collectionResult.status === 'fulfilled') {
          setCollection(collectionResult.value)
        } else {
          setError(t('collections.loadFailed'))
        }
        if (runsResult.status === 'fulfilled') {
          setRuns(runsResult.value)
        }
      })
      .finally(() => setLoading(false))
  }, [collectionId, t])

  const handleGenerate = async () => {
    if (!collection || generating) return
    setGenerating(true)
    setError(null)
    try {
      const skill = await generateCollectionSkill(collection.id, {
        user_goal: userGoal.trim() || null,
        reuse_extracted_kus: true,
        detect_conflicts: true,
      })
      router.push(`/collections/${collection.id}/skills/${skill.id}`)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('collections.generateFailed')
      setError(msg)
      setGenerating(false)
    }
  }

  const handleRetry = async (run: CollectionSkillRun) => {
    if (retryingRunId) return
    setRetryingRunId(run.id)
    setError(null)
    try {
      const skill = await retryCollectionSkill(run.id, {
        user_goal: userGoal.trim() || null,
        detect_conflicts: true,
      })
      router.push(`/collections/${collection?.id || collectionId}/skills/${skill.id}`)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('collections.generateFailed')
      setError(msg)
    } finally {
      setRetryingRunId(null)
    }
  }

  const handleDelete = async () => {
    if (!collection || deleting) return
    if (!confirm(t('collections.deleteConfirm', { name: collection.name }))) return
    setDeleting(true)
    setError(null)
    try {
      await deleteCollection(collection.id)
      router.push('/library')
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('collections.deleteFailed')
      setError(msg)
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', color: 'var(--text-muted)' }}>
        <Loader2 size={28} style={{ animation: 'spin 1.4s linear infinite' }} />
      </main>
    )
  }

  return (
    <main style={{ maxWidth: '760px', margin: '0 auto', padding: '48px 24px 120px' }}>
      <Link
        href="/library"
        style={{
          display: 'inline-flex',
          gap: '6px',
          alignItems: 'center',
          color: 'var(--text-muted)',
          fontSize: 'var(--text-xs)',
          textDecoration: 'none',
          marginBottom: '24px',
        }}
      >
        <ArrowLeft size={12} />
        {t('common.backToLibrary')}
      </Link>

      {error && <div className="alert-error">{error}</div>}

      {collection && (
        <>
          <header style={{
            marginBottom: '40px',
            display: 'flex',
            justifyContent: 'space-between',
            gap: '24px',
            alignItems: 'flex-start',
            flexWrap: 'wrap',
          }}>
            <div style={{ minWidth: 0, flex: '1 1 360px' }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: 'var(--text-muted)',
                fontSize: 'var(--text-xs)',
                marginBottom: '8px',
              }}>
                <Layers size={14} />
                {t('collections.title')}
              </div>
              <h1 className="serif" style={{ fontSize: 'var(--text-2xl)', marginBottom: '8px' }}>
                {collection.name}
              </h1>
              {collection.description && (
                <p style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)' }}>
                  {collection.description}
                </p>
              )}
            </div>
            <div style={{ display: 'grid', gap: '8px', minWidth: '220px', maxWidth: '280px' }}>
              <input
                value={userGoal}
                onChange={e => setUserGoal(e.target.value)}
                placeholder={t('collections.userGoalPlaceholder')}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: '6px',
                  background: 'var(--bg)',
                  color: 'var(--text-primary)',
                  font: 'inherit',
                  fontSize: 'var(--text-xs)',
                  padding: '10px 12px',
                  outline: 'none',
                }}
              />
              <button className="btn-primary" disabled={generating} onClick={handleGenerate}>
                {generating && <Loader2 size={14} style={{ animation: 'spin 1.4s linear infinite' }} />}
                {generating ? t('collections.generating') : t('collections.generate')}
              </button>
              <button
                className="btn-ghost"
                disabled={deleting}
                onClick={handleDelete}
                style={{
                  color: 'var(--status-error)',
                  justifyContent: 'center',
                }}
              >
                {deleting ? (
                  <Loader2 size={14} style={{ animation: 'spin 1.4s linear infinite' }} />
                ) : (
                  <Trash2 size={14} />
                )}
                {deleting ? t('collections.deleting') : t('collections.delete')}
              </button>
            </div>
          </header>

          <section>
            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 500, marginBottom: '12px' }}>
              {t('collections.sourceBooks')}
            </h2>
            <div style={{ borderTop: '1px solid var(--border)' }}>
              {collection.books.map(book => (
                <div
                  key={book.book_id}
                  style={{
                    borderBottom: '1px solid var(--border)',
                    padding: '16px 0',
                    display: 'flex',
                    gap: '12px',
                    alignItems: 'center',
                  }}
                >
                  <div style={{
                    width: '30px',
                    height: '30px',
                    borderRadius: '6px',
                    border: '1px solid var(--border)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <BookOpen size={14} />
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>
                      {book.title || t('common.unknownBookTitle')}
                    </div>
                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '4px' }}>
                      {book.author || ''}{book.page_count ? ` · ${book.page_count} ${t('common.pageUnit')}` : ''}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section style={{ marginTop: '40px' }}>
            <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 500, marginBottom: '12px' }}>
              {t('collections.runs')}
            </h2>
            {runs.length === 0 ? (
              <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
                {t('collections.noRuns')}
              </p>
            ) : (
              <div style={{ borderTop: '1px solid var(--border)' }}>
                {runs.map(run => {
                  const statusLabel =
                    run.status === 'ready' ? t('collections.runReady') :
                    run.status === 'generating' ? t('collections.runGenerating') :
                    run.status === 'error' ? t('collections.runError') :
                    t('collections.runUnknown')
                  return (
                    <div
                      key={run.id}
                      style={{
                        borderBottom: '1px solid var(--border)',
                        padding: '14px 0',
                        display: 'grid',
                        gap: '8px',
                      }}
                    >
                      <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        gap: '12px',
                        alignItems: 'center',
                        flexWrap: 'wrap',
                      }}>
                        <div>
                          <div style={{ fontSize: 'var(--text-sm)', fontWeight: 500 }}>{statusLabel}</div>
                          <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', marginTop: '4px' }}>
                            {new Date(run.created_at).toLocaleString()}
                            {run.pipeline_phase ? ` · ${t('collections.phaseLabel')}: ${run.pipeline_phase}` : ''}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                          <Link className="btn-secondary" href={`/collections/${collection.id}/skills/${run.id}`}>
                            {t('collections.viewRun')}
                          </Link>
                          {run.is_retryable && (
                            <button
                              className="btn-secondary"
                              onClick={() => handleRetry(run)}
                              disabled={retryingRunId === run.id}
                            >
                              {retryingRunId === run.id ? t('collections.generating') : t('collections.retryRun')}
                            </button>
                          )}
                        </div>
                      </div>
                      {run.failed_reason && (
                        <div style={{ color: 'var(--status-error)', fontSize: 'var(--text-xs)' }}>
                          {t('collections.failureReason')}: {run.failed_reason}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        </>
      )}
    </main>
  )
}
