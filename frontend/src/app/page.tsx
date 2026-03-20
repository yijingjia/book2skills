'use client'

import { useState, useCallback, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useDropzone } from 'react-dropzone'
import { Upload, Library, ArrowRight, Loader2, CheckCircle, Cpu } from 'lucide-react'
import { motion, AnimatePresence, Variants } from 'framer-motion'
import { uploadBook, getBookStatus, generateSkill } from '@/lib/api'
import { LanguageSwitcher } from '@/components/language-switcher'
import { useI18n } from '@/lib/i18n'

type Step = 'upload' | 'processing' | 'ready' | 'generating'

// Animation variants
const fadeInUp: Variants = {
  initial: { opacity: 0, y: 15 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.16, 1, 0.3, 1] as any } }
}

const staggerContainer: Variants = {
  animate: {
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.1
    }
  }
}

const stepVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.16, 1, 0.3, 1] as any } },
  exit: { opacity: 0, y: -10, transition: { duration: 0.3, ease: 'easeIn' } }
}

export default function HomePage() {
  const { t } = useI18n()
  const router = useRouter()
  const [step, setStep] = useState<Step>('upload')
  const [bookId, setBookId] = useState<string | null>(null)
  const [bookTitle, setBookTitle] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  const onDrop = useCallback(async (files: File[]) => {
    const file = files[0]
    if (!file) return
    stopPolling()
    setError(null)
    setStep('processing')

    try {
      const { book_id } = await uploadBook(file)
      setBookId(book_id)

      pollRef.current = setInterval(async () => {
        try {
          const status = await getBookStatus(book_id)
          if (status.status === 'ready') {
            stopPolling()
            setBookTitle(status.title)
            setStep('ready')
          } else if (status.status === 'error') {
            stopPolling()
            setError(status.error_message || t('home.error.processFailed'))
            setStep('upload')
          }
        } catch (e: any) {
          stopPolling()
          setError(e?.message || t('home.error.processFailed'))
          setStep('upload')
        }
      }, 2000)
    } catch (e: any) {
      stopPolling()
      setError(e.message || t('home.error.uploadFailed'))
      setStep('upload')
    }
  }, [stopPolling, t])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'], 'application/epub+zip': ['.epub'] },
    maxFiles: 1,
    disabled: step !== 'upload',
  })

  const handleGenerate = async () => {
    if (!bookId) return
    setStep('generating')
    try {
      const skill = await generateSkill(bookId)
      router.push(`/books/${bookId}/skills/${skill.id}`)
    } catch (e: any) {
      setError(e.message || t('home.error.generateFailed'))
      setStep('ready')
    }
  }

  return (
    <main style={{
      minHeight: '100vh',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Nav */}
      <nav style={{
        padding: '20px 40px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        borderBottom: '1px solid var(--border)',
      }}>
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: '1.1rem',
            color: 'var(--text-primary)',
            letterSpacing: '-0.01em',
          }}>
          book2skills
        </motion.span>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              color: 'var(--text-secondary)',
              fontSize: 'var(--text-sm)',
              textDecoration: 'none',
              transition: 'color 0.15s ease',
            }}
          >
            <Link
              href="/library"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                color: 'var(--text-secondary)',
                fontSize: 'var(--text-sm)',
                textDecoration: 'none',
                transition: 'color 0.15s ease',
              }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--text-primary)')}
              onMouseLeave={e => (e.currentTarget.style.color = 'var(--text-secondary)')}
            >
              <Library size={14} strokeWidth={1.5} />
              {t('home.navLibrary')}
            </Link>
          </motion.div>
          <LanguageSwitcher />
        </div>
      </nav>

      {/* Content */}
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 24px',
      }}>
        <motion.div
          variants={staggerContainer}
          initial="initial"
          animate="animate"
          style={{ width: '100%', maxWidth: '520px' }}>

          {/* Hero */}
          <motion.div variants={fadeInUp} style={{ marginBottom: '48px' }}>
            <p style={{
              fontSize: '11px',
              fontWeight: 500,
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
              color: 'var(--text-muted)',
              marginBottom: '20px',
            }}>
              {t('home.heroEyebrow')}
            </p>

            <h1 style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 'clamp(2rem, 5vw, 2.75rem)',
              fontWeight: 400,
              lineHeight: 1.2,
              letterSpacing: '-0.02em',
              color: 'var(--text-primary)',
              marginBottom: '16px',
            }}>
              {t('home.heroTitleLine1')}<br />
              <em style={{ color: 'var(--accent)', fontStyle: 'italic' }}>{t('home.heroTitleLine2')}</em>
            </h1>

            <p style={{
              fontSize: 'var(--text-base)',
              color: 'var(--text-secondary)',
              lineHeight: 1.7,
              maxWidth: 'var(--content-max-width)',
            }}>
              {t('home.heroDesc')}
            </p>
          </motion.div>

          {/* Error */}
          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                className="alert-error"
                style={{ marginBottom: '24px', overflow: 'hidden' }}
              >
                {error}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Upload Card */}
          <motion.div
            variants={fadeInUp}
            style={{
              background: 'var(--bg-subtle)',
              border: '1px solid var(--border)',
              borderRadius: '12px',
              padding: '2px',
              marginBottom: '32px',
            }}>

            <div style={{ position: 'relative', minHeight: '180px' }}>
              <AnimatePresence mode="wait">
                {step === 'upload' && (
                  <motion.div
                    key="upload"
                    variants={stepVariants}
                    initial="initial"
                    animate="animate"
                    exit="exit"
                  >
                    <div
                      {...getRootProps()}
                      className={`drop-zone ${isDragActive ? 'active' : ''}`}
                      style={{
                        margin: '0',
                        borderRadius: '10px',
                        border: `1px dashed ${isDragActive ? 'var(--accent-border)' : 'var(--border-hover)'}`,
                        background: isDragActive ? 'var(--accent-dim)' : 'transparent',
                        padding: '52px 32px',
                        transition: 'all 0.2s ease',
                      }}
                    >
                      <input {...getInputProps()} />
                      <div style={{ textAlign: 'center' }}>
                        <Upload
                          size={28}
                          strokeWidth={1}
                          style={{
                            color: isDragActive ? 'var(--accent)' : 'var(--text-muted)',
                            marginBottom: '16px',
                            transition: 'color 0.2s ease',
                          }}
                        />
                        <p style={{
                          fontSize: '14px',
                          fontWeight: 500,
                          color: 'var(--text-primary)',
                          marginBottom: '6px',
                        }}>
                          {isDragActive ? t('home.drop.active') : t('home.drop.idle')}
                        </p>
                        <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                          {t('home.drop.hint')}
                        </p>
                      </div>
                    </div>
                  </motion.div>
                )}

                {step === 'processing' && (
                  <motion.div
                    key="processing"
                    variants={stepVariants}
                    initial="initial"
                    animate="animate"
                    exit="exit"
                    style={{ textAlign: 'center', padding: '52px 32px' }}>
                    <motion.div
                      animate={{ rotate: 360 }}
                      transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
                      style={{ display: 'inline-block', marginBottom: '16px' }}
                    >
                      <Loader2
                        size={24}
                        strokeWidth={1.5}
                        style={{ color: 'var(--text-muted)' }}
                      />
                    </motion.div>
                    <p style={{ fontSize: '14px', fontWeight: 500, marginBottom: '6px' }}>
                      {t('home.processing.title')}
                    </p>
                    <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {t('home.processing.desc')}
                    </p>
                  </motion.div>
                )}

                {step === 'ready' && bookTitle && (
                  <motion.div
                    key="ready"
                    variants={stepVariants}
                    initial="initial"
                    animate="animate"
                    exit="exit"
                    style={{ padding: '40px 32px' }}>
                    <div style={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: '14px',
                      marginBottom: '28px',
                    }}>
                      <CheckCircle
                        size={20}
                        strokeWidth={1.5}
                        style={{ color: 'var(--status-ok)', flexShrink: 0, marginTop: '2px' }}
                      />
                      <div>
                        <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                          {t('home.ready.title')}
                        </p>
                        <p style={{ fontSize: '15px', fontWeight: 500, fontFamily: 'var(--font-serif)' }}>
                          《{bookTitle}》
                        </p>
                      </div>
                    </div>
                    <motion.button
                      whileHover={{ scale: 1.01 }}
                      whileTap={{ scale: 0.98 }}
                      className="btn-primary"
                      onClick={handleGenerate}
                      style={{ width: '100%', justifyContent: 'center' }}
                    >
                      {t('home.ready.generate')}
                      <ArrowRight size={14} strokeWidth={2} />
                    </motion.button>
                  </motion.div>
                )}

                {step === 'generating' && (
                  <motion.div
                    key="generating"
                    variants={stepVariants}
                    initial="initial"
                    animate="animate"
                    exit="exit"
                    style={{ textAlign: 'center', padding: '52px 32px' }}>
                    <motion.div
                      animate={{
                        opacity: [0.4, 1, 0.4],
                        scale: [0.95, 1.05, 0.95],
                      }}
                      transition={{
                        repeat: Infinity,
                        duration: 2,
                        ease: "easeInOut",
                      }}
                      style={{ display: 'inline-block', marginBottom: '16px' }}
                    >
                      <Cpu
                        size={24}
                        strokeWidth={1}
                        style={{ color: 'var(--accent)' }}
                      />
                    </motion.div>
                    <p style={{ fontSize: '14px', fontWeight: 500, marginBottom: '6px' }}>
                      {t('home.generating.title')}
                    </p>
                    <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {t('home.generating.desc')}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>

          {/* Feature pills */}
          <motion.div
            variants={fadeInUp}
            style={{
              display: 'flex',
              gap: '0',
              borderTop: '1px solid var(--border)',
              paddingTop: '24px',
            }}>
            {[
              { label: t('home.feature.grounded.label'), desc: t('home.feature.grounded.desc') },
              { label: t('home.feature.refine.label'), desc: t('home.feature.refine.desc') },
              { label: t('home.feature.install.label'), desc: t('home.feature.install.desc') },
            ].map((f, i) => (
              <div
                key={f.label}
                style={{
                  flex: 1,
                  paddingRight: i < 2 ? 'var(--space-4)' : '0',
                  borderRight: i < 2 ? '1px solid var(--border)' : 'none',
                  marginRight: i < 2 ? 'var(--space-4)' : '0',
                }}
              >
                <p style={{ fontSize: 'var(--text-sm)', fontWeight: 500, marginBottom: 'var(--space-1)', color: 'var(--text-primary)' }}>
                  {f.label}
                </p>
                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  {f.desc}
                </p>
              </div>
            ))}
          </motion.div>

        </motion.div>
      </div>
    </main>
  )
}
