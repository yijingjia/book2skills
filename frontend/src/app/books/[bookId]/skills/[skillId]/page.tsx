'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter, useParams } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import { ArrowLeft, Download, RefreshCw, FileText, Sparkles, Loader2, AlertCircle } from 'lucide-react'
import { getSkill, packSkill, getDownloadUrl, refineSkillStream, generateSkill } from '@/lib/api'
import { useI18n } from '@/lib/i18n'

type SkillData = {
  id: string
  book_id: string
  skill_md: string | null
  scripts: Record<string, unknown> | null
  zip_path: string | null
  status: string
  version: number
}

export default function SkillPage() {
  const MAX_POLL_FAILURES = 3
  const { t } = useI18n()
  const router = useRouter()
  const params = useParams()
  const skillId = params.skillId as string

  const [skill, setSkill] = useState<SkillData | null>(null)
  const [loading, setLoading] = useState(true)
  const [packing, setPacking] = useState(false)
  const [zipReady, setZipReady] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [refining, setRefining] = useState(false)
  const [liveText, setLiveText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [partialReport, setPartialReport] = useState<{ total: number; generated: number; failed: number } | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollFailureRef = useRef(0)

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const applySkillData = (data: SkillData) => {
    setSkill(data)
    if (data.zip_path) setZipReady(true)
    pollFailureRef.current = 0

    const reportRaw = data.scripts?.['generation_report.json']
    if (typeof reportRaw === 'string' || (typeof reportRaw === 'object' && reportRaw !== null)) {
      try {
        const report = typeof reportRaw === 'string' ? JSON.parse(reportRaw) : reportRaw
        const failed = Number(report.failed_modules || 0)
        if (failed > 0) {
          setPartialReport({
            total: Number(report.total_modules || 0),
            generated: Number(report.generated_modules || 0),
            failed,
          })
        } else {
          setPartialReport(null)
        }
      } catch {
        setPartialReport(null)
      }
    } else {
      setPartialReport(null)
    }
  }

  useEffect(() => {
    if (!skillId) return

    const loadData = () => {
      getSkill(skillId)
        .then(data => {
          applySkillData(data)
          if (data.status !== 'generating') {
            stopPolling()
          }
        })
        .catch(() => {
          pollFailureRef.current += 1
          setError('skill.error.loadFailed')
          if (pollFailureRef.current >= MAX_POLL_FAILURES) {
            stopPolling()
          }
        })
        .finally(() => setLoading(false))
    }

    loadData()
    pollRef.current = setInterval(loadData, 2000)

    return () => stopPolling()
  }, [skillId])

  const handlePack = async () => {
    if (!skillId) return
    setPacking(true)
    try {
      await packSkill(skillId)
      setZipReady(true)
    } catch (e: any) {
      setError(e.message || t('skill.error.packFailed'))
    } finally {
      setPacking(false)
    }
  }

  const handleRegenerate = async () => {
    if (!skill?.book_id) return
    if (!confirm(t('skill.regenerateConfirm'))) return
    
    setRegenerating(true)
    setError(null)
    try {
      const res = await generateSkill(skill.book_id)
      router.push(`/books/${skill.book_id}/skills/${res.id}`)
    } catch (e: any) {
      setError(e.message || t('skill.error.regenerateFailed'))
      setRegenerating(false)
    }
  }

  const handleRefine = async () => {
    if (!instruction.trim() || !skillId) return
    setRefining(true)
    setLiveText('')
    setError(null)
    let full = ''
    try {
      for await (const chunk of refineSkillStream(skillId, instruction)) {
        full += chunk
        setLiveText(full)
      }
      const updated = await getSkill(skillId)
      applySkillData(updated)
      setInstruction('')
    } catch (e: any) {
      setError(e.message || t('skill.error.refineFailed'))
    } finally {
      setRefining(false)
      setLiveText('')
    }
  }

  const handleDownload = () => {
    if (!skillId) return
    const url = getDownloadUrl(skillId)
    const a = document.createElement('a')
    a.href = url
    a.download = 'skills.zip'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  if (loading) {
    return (
      <main style={centeredStyle}>
        <div style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
          <Loader2 size={32} strokeWidth={1.5} style={{ animation: 'spin 1.4s linear infinite', marginBottom: '16px' }} />
          <p style={{ fontSize: 'var(--text-sm)' }}>{t('skill.initAssets')}</p>
        </div>
      </main>
    )
  }

  return (
    <main style={{ maxWidth: 'var(--page-max-width)', margin: '0 auto', padding: '48px 24px 120px' }}>
      
      {/* Header */}
      <header style={{ marginBottom: '48px' }}>
        <Link 
          href="/library" 
          style={{ 
            display: 'inline-flex', 
            alignItems: 'center', 
            gap: '6px', 
            color: 'var(--text-muted)', 
            fontSize: 'var(--text-xs)', 
            textDecoration: 'none',
            marginBottom: '16px',
            transition: 'color 0.15s ease'
          }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--text-muted)'}
        >
          <ArrowLeft size={12} />
          {t('common.backToLibrary')}
        </Link>
        
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '24px' }}>
          <div>
            <h1 className="serif" style={{ fontSize: 'var(--text-2xl)', marginBottom: '4px' }}>
              {t('skill.title')}
            </h1>
            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
              {skill?.status === 'ready'
                ? t('skill.versionReady', { version: skill?.version ?? '-' })
                : t('skill.versionBuilding', { version: skill?.version ?? '-' })}
            </p>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              className="btn-secondary"
              onClick={handleRegenerate}
              disabled={regenerating}
              style={{ fontSize: 'var(--text-xs)', padding: '8px 14px' }}
            >
              <RefreshCw size={13} style={{ animation: regenerating ? 'spin 2s linear infinite' : 'none' }} />
              {t('skill.regenerate')}
            </button>
            
            {!zipReady ? (
              <button
                className="btn-primary"
                onClick={handlePack}
                disabled={packing || skill?.status === 'generating'}
                style={{ fontSize: 'var(--text-xs)', padding: '8px 16px' }}
              >
                {packing ? (
                  <><Loader2 size={13} style={{ animation: 'spin 1.4s linear infinite' }} /> {t('skill.packing')}</>
                ) : (
                  <><Download size={13} /> {t('skill.exportZip')}</>
                )}
              </button>
            ) : (
              <button
                onClick={handleDownload}
                className="btn-primary"
                style={{ fontSize: 'var(--text-xs)', padding: '8px 16px' }}
              >
                <Download size={13} /> {t('skill.downloadZip')}
              </button>
            )}
          </div>
        </div>
      </header>

      {error && (
        <div className="alert-error" style={{ marginBottom: '32px' }}>
          <AlertCircle size={14} />
          {error.startsWith('skill.') ? t(error) : error}
        </div>
      )}

      {partialReport && (
        <div
          style={{
            marginBottom: '24px',
            border: '1px solid #7c5f1a',
            background: 'rgba(167, 129, 41, 0.12)',
            color: 'var(--text-secondary)',
            borderRadius: '10px',
            padding: '12px 14px',
            fontSize: '13px',
            lineHeight: 1.6,
          }}
        >
          <strong style={{ color: 'var(--text-primary)' }}>{t('skill.partialWarningTitle')}</strong>
          <div>
            {t('skill.partialWarningDesc', {
              generated: partialReport.generated,
              total: partialReport.total,
              failed: partialReport.failed,
            })}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '48px', alignItems: 'start' }}>
        
        {/* SKILL.md Preview */}
        <section>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
            <FileText size={16} strokeWidth={1.5} style={{ color: 'var(--text-muted)' }} />
            <h2 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, letterSpacing: '0.02em', textTransform: 'uppercase', opacity: 0.6 }}>
              {t('skill.preview')}
            </h2>
          </div>

          <div style={{ 
            background: 'var(--bg-raised)', 
            border: '1px solid var(--border)', 
            borderRadius: '12px',
            overflow: 'hidden'
          }}>
            {skill?.status === 'generating' ? (
              <div style={{ textAlign: 'center', padding: '80px 40px', color: 'var(--text-muted)' }}>
                <Loader2 size={32} strokeWidth={1} style={{ animation: 'spin 1.5s linear infinite', marginBottom: '16px', opacity: 0.3 }} />
                <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-secondary)' }}>{t('skill.generatingTitle')}</p>
                <p style={{ fontSize: 'var(--text-xs)', marginTop: '8px', opacity: 0.6 }}>{t('skill.generatingDesc')}</p>
              </div>
            ) : (
              <div className="custom-markdown reading-width" style={{
                padding: '40px',
                fontSize: '15.5px', // Slightly smaller for dense doc
                maxHeight: '70vh',
                overflowY: 'auto'
              }}>
                <ReactMarkdown 
                  remarkPlugins={[remarkGfm]} 
                  rehypePlugins={[rehypeRaw, rehypeSanitize]}
                >
                  {skill?.skill_md || t('skill.emptyDefinition')}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </section>

        {/* Refinement Panel */}
        <aside style={{ position: 'sticky', top: '48px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
            <Sparkles size={16} strokeWidth={1.5} style={{ color: 'var(--accent)' }} />
            <h2 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, letterSpacing: '0.02em', textTransform: 'uppercase', opacity: 0.6 }}>
              {t('skill.refineTitle')}
            </h2>
          </div>

          <div style={{ 
            background: 'var(--bg-raised)', 
            border: '1px solid var(--border)', 
            borderRadius: '12px',
            padding: '24px'
          }}>
            <p style={{ color: 'var(--text-secondary)', fontSize: '13px', lineHeight: 1.6, marginBottom: '20px' }}>
              {t('skill.refineDesc')}
            </p>

            {liveText && (
              <div style={{
                fontSize: '11px',
                fontFamily: 'monospace',
                background: 'rgba(0,0,0,0.3)',
                padding: '12px',
                borderRadius: '6px',
                marginBottom: '16px',
                maxHeight: '200px',
                overflowY: 'auto',
                color: 'var(--text-secondary)',
                border: '1px solid var(--border)'
              }}>
                {liveText}
              </div>
            )}

            <textarea
              ref={textareaRef}
              value={instruction}
              onChange={e => setInstruction(e.target.value)}
              placeholder={t('skill.refinePlaceholder')}
              disabled={refining}
              style={{
                width: '100%', 
                minHeight: '100px', 
                padding: '14px',
                background: 'var(--bg)', 
                border: '1px solid var(--border)',
                borderRadius: '8px', 
                color: 'var(--text-primary)', 
                fontSize: '14px',
                resize: 'none', 
                outline: 'none', 
                marginBottom: '16px', 
                boxSizing: 'border-box',
                transition: 'border-color 0.2s ease'
              }}
              onFocus={e => e.currentTarget.style.borderColor = 'var(--border-hover)'}
              onBlur={e => e.currentTarget.style.borderColor = 'var(--border)'}
            />

            <button
              className="btn-primary"
              onClick={handleRefine}
              disabled={refining || !instruction.trim() || skill?.status === 'generating'}
              style={{ width: '100%', justifyContent: 'center', height: '42px' }}
            >
              {refining ? (
                <><Loader2 size={14} style={{ animation: 'spin 1.4s linear infinite' }} /> {t('skill.refining')}</>
              ) : (
                t('skill.updateDefinition')
              )}
            </button>
          </div>
        </aside>

      </div>
    </main>
  )
}

const centeredStyle: React.CSSProperties = {
  minHeight: '100vh',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}
