'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import { ArrowLeft, Download, Loader2, Package } from 'lucide-react'
import {
  CollectionSkill,
  getCollectionSkill,
  getCollectionSkillDownloadUrl,
  packCollectionSkill,
} from '@/lib/api'
import { useI18n } from '@/lib/i18n'

export default function CollectionSkillPreviewPage() {
  const { t } = useI18n()
  const params = useParams()
  const collectionId = params.collectionId as string
  const skillId = params.skillId as string

  const [skill, setSkill] = useState<CollectionSkill | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [packing, setPacking] = useState(false)
  const [packed, setPacked] = useState(false)

  useEffect(() => {
    if (!skillId) return
    getCollectionSkill(skillId)
      .then(s => {
        setSkill(s)
        if (s.zip_path) setPacked(true)
      })
      .catch(() => setError(t('skill.error.loadFailed')))
      .finally(() => setLoading(false))
  }, [skillId, t])

  useEffect(() => {
    if (!skill || skill.status !== 'generating') return
    const timer = setInterval(() => {
      getCollectionSkill(skillId)
        .then(s => {
          setSkill(s)
          if (s.zip_path) setPacked(true)
        })
        .catch(() => {})
    }, 2000)
    return () => clearInterval(timer)
  }, [skill?.status, skillId])

  const handlePack = async () => {
    if (!skill || packing) return
    setPacking(true)
    setError(null)
    try {
      await packCollectionSkill(skill.id)
      setPacked(true)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : t('skill.error.packFailed')
      setError(msg)
    } finally {
      setPacking(false)
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
        href={`/collections/${collectionId}`}
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

      {error && <div className="alert-error" style={{ marginBottom: '24px' }}>{error}</div>}

      {skill && skill.status === 'generating' && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)' }}>
          <Loader2 size={28} style={{ animation: 'spin 1.4s linear infinite', margin: '0 auto 16px' }} />
          <p style={{ fontSize: 'var(--text-sm)' }}>{t('skill.generatingTitle')}</p>
        </div>
      )}

      {skill && skill.status !== 'generating' && (
        <>
          <header style={{ marginBottom: '32px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
            <h1 className="serif" style={{ fontSize: 'var(--text-2xl)' }}>
              {t('skill.preview')}
            </h1>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {!packed && skill.status === 'ready' && (
                <button className="btn-secondary" onClick={handlePack} disabled={packing}>
                  {packing
                    ? <><Loader2 size={14} style={{ animation: 'spin 1.4s linear infinite' }} />{t('skill.packing')}</>
                    : <><Package size={14} />{t('skill.exportZip')}</>
                  }
                </button>
              )}
              {packed && (
                <a
                  href={getCollectionSkillDownloadUrl(skill.id)}
                  className="btn-primary"
                  style={{ textDecoration: 'none', display: 'inline-flex', gap: '6px', alignItems: 'center' }}
                >
                  <Download size={14} />
                  {t('skill.downloadZip')}
                </a>
              )}
            </div>
          </header>

          {skill.skill_md ? (
            <pre style={{
              background: 'var(--bg-raised)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              padding: '20px',
              fontSize: 'var(--text-xs)',
              lineHeight: 1.6,
              overflowX: 'auto',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              color: 'var(--text-primary)',
            }}>
              {skill.skill_md}
            </pre>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>
              {t('skill.emptyDefinition')}
            </p>
          )}
        </>
      )}
    </main>
  )
}
