'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

export type Locale = 'zh' | 'en'
type Params = Record<string, string | number>
type Dictionary = Record<string, string>

const LOCALE_STORAGE_KEY = 'book2skills.locale'
export const LOCALE_COOKIE_KEY = 'book2skills.locale'

const dictionaries: Record<Locale, Dictionary> = {
  zh: {
    'meta.title': 'book2skills - 将书转化为 AI 技能',
    'meta.description': '上传 EPUB 书籍，AI 自动提炼方法论，生成可安装到 AI Agent 的技能包。',
    'language.zh': '中',
    'language.en': 'EN',
    'common.appName': 'book2skills',
    'common.library': '书库',
    'common.backToLibrary': '返回书库',
    'common.loading': '加载中',
    'common.unknownBookTitle': '未知书名',
    'common.pageUnit': '页',
    'common.chapterDefault': '正文章节',
    'home.navLibrary': '书库',
    'home.heroEyebrow': 'Knowledge Extraction Engine',
    'home.heroTitleLine1': '将书籍转化为',
    'home.heroTitleLine2': 'Agent 可执行的技能',
    'home.heroDesc': '上传 EPUB，AI 深度解析方法论结构，生成可安装到 Claude / Cursor 的 skills.zip 技能包。',
    'home.drop.active': '松开以上传',
    'home.drop.idle': '拖拽或点击上传',
    'home.drop.hint': '支持 EPUB，最大 50 MB',
    'home.processing.title': '解析书籍结构中',
    'home.processing.desc': '提取章节 · 构建语义索引 · 约 1-2 分钟',
    'home.ready.title': '解析完成',
    'home.ready.generate': '生成 skills.zip',
    'home.generating.title': '正在提炼方法论',
    'home.generating.desc': '生成 SKILL.md · 构建 references/ · 打包技能',
    'home.feature.grounded.label': '防幻觉',
    'home.feature.grounded.desc': '每条输出附原文引用',
    'home.feature.refine.label': '对话精炼',
    'home.feature.refine.desc': '自然语言迭代调整',
    'home.feature.install.label': '直接安装',
    'home.feature.install.desc': 'Claude · Cursor · 自建 Agent',
    'home.error.processFailed': '处理失败',
    'home.error.uploadFailed': '上传失败',
    'home.error.generateFailed': '生成失败',
    'library.uploadNewBook': '上传新书',
    'library.title': '书库',
    'library.summary': '共 {total} 本 · {ready} 本已处理完成',
    'library.loading': '加载中',
    'library.loadFailed': '加载书库失败，请检查后端连接',
    'library.empty': '还没有上传任何书籍',
    'library.uploadFirst': '上传第一本书',
    'library.chatWithBook': '与书对话',
    'library.viewSkill': '查看技能',
    'library.generateSkill': '生成技能',
    'library.retrying': '重试中',
    'library.retry': '重新生成',
    'library.error.regenerateFailed': '重新生成失败',
    'library.status.pending': '等待处理',
    'library.status.processing': '解析中',
    'library.status.ready': '已就绪',
    'library.status.error': '失败',
    'library.skill.generating': '技能生成中',
    'library.skill.ready': '技能已生成',
    'library.skill.error': '技能生成失败',
    'collections.title': '书单',
    'collections.librarySection': '书单',
    'collections.allTitle': '全部书单',
    'collections.new': '新建书单',
    'collections.viewAll': '查看全部',
    'collections.create': '创建书单',
    'collections.name': '书单名称',
    'collections.description': '描述',
    'collections.selectBooks': '选择书籍',
    'collections.readyBooksOnly': '只能选择已处理完成的书',
    'collections.selectedCount': '已选择 {count} 本',
    'collections.createFailed': '创建书单失败',
    'collections.loadFailed': '加载书单失败',
    'collections.empty': '还没有书单',
    'collections.bookCount': '{count} 本书',
    'collections.generateComingSoon': '综合技能生成将在下一阶段开放',
    'collections.sourceBooks': '来源书籍',
    'collections.generate': '生成综合 Skill',
    'collections.generating': '生成中',
    'collections.userGoal': '生成目标',
    'collections.userGoalPlaceholder': '例如：适合早期创业团队做需求验证',
    'collections.generateFailed': '生成综合 Skill 失败',
    'chat.bookLoading': '读取中...',
    'chat.semanticLoaded': '全文化语义索引已加载',
    'chat.mode.rag.title': '原著问答',
    'chat.mode.rag.desc': '基于向量数据库溯源，确保回答防幻觉并附带原文引用。',
    'chat.mode.agent.title': '技能推演',
    'chat.mode.agent.desc': '加载 SKILL.md，按提炼的方法论框架指导现实任务破局。',
    'chat.empty.rag.title': '开始向原著溯源发问',
    'chat.empty.agent.title': '进入沙盘推演场',
    'chat.empty.rag.desc': '询问书中的核心术语、逻辑关系或章节细节，AI 将精准锁定原文进行答复。',
    'chat.empty.agent.desc': '抛出一个具体的现实痛点，观察 AI 如何运用已提炼的方法论系统为你提供解法。',
    'chat.input.rag': '提问原著细节...',
    'chat.input.agent': '描述场景痛点，请求技能指导...',
    'chat.source.title': '原文溯源依据',
    'chat.source.count': '已溯源到 {count} 处原著文本',
    'chat.error.answerFailed': '无法获取回答：{message}',
    'chat.error.agentNoSkill': '暂无技能包记录。请先生成技能包以开启推演模式。',
    'chat.error.refineException': '[精炼执行异常] {message}',
    'chat.thinking.rag.1': '正在检索原文',
    'chat.thinking.rag.2': '向量匹配中',
    'chat.thinking.rag.3': '溯源上下文',
    'chat.thinking.rag.4': '组织回答',
    'chat.thinking.agent.1': '加载技能包',
    'chat.thinking.agent.2': '分析场景',
    'chat.thinking.agent.3': '推演方案',
    'chat.thinking.agent.4': '生成建议',
    'skill.initAssets': '初始化核心资产...',
    'skill.title': '技能包详情',
    'skill.versionReady': '版本 v{version} · 编译就绪',
    'skill.versionBuilding': '版本 v{version} · 构建中',
    'skill.regenerate': '重新生成',
    'skill.packing': '打包中',
    'skill.exportZip': '导出 ZIP 技能包',
    'skill.downloadZip': '下载技能包',
    'skill.preview': 'SKILL.md 预览',
    'skill.generatingTitle': '正在提炼工作流',
    'skill.generatingDesc': 'AI 正在深度解析语义并结构化技能定义',
    'skill.emptyDefinition': '（尚未生成有效定义）',
    'skill.refineTitle': '对话精炼',
    'skill.refineDesc': '通过对话微调技能定义。你可以要求 AI 聚焦特定章节或是调整输出风格。',
    'skill.refinePlaceholder': '例如："增加对第三章核心公式的引用"',
    'skill.refining': '正在调整...',
    'skill.updateDefinition': '更新技能定义',
    'skill.error.loadFailed': '加载技能失败',
    'skill.error.packFailed': '打包失败',
    'skill.error.regenerateFailed': '重新生成失败',
    'skill.error.refineFailed': '精炼失败',
    'skill.partialWarningTitle': '部分模块生成失败',
    'skill.partialWarningDesc': '本次共生成 {generated}/{total} 个模块，{failed} 个模块失败并已跳过。当前技能包仍可使用。',
    'skill.regenerateConfirm': '重新生成将会创建一个完全新的技能包记录。确定要继续吗？',
  },
  en: {
    'meta.title': 'book2skills - Turn Books Into AI Skills',
    'meta.description': 'Upload EPUB books, let AI extract methods, and generate installable skill packages for AI agents.',
    'language.zh': 'ZH',
    'language.en': 'EN',
    'common.appName': 'book2skills',
    'common.library': 'Library',
    'common.backToLibrary': 'Back to Library',
    'common.loading': 'Loading',
    'common.unknownBookTitle': 'Untitled Book',
    'common.pageUnit': 'pages',
    'common.chapterDefault': 'Main Chapter',
    'home.navLibrary': 'Library',
    'home.heroEyebrow': 'Knowledge Extraction Engine',
    'home.heroTitleLine1': 'Transform books into',
    'home.heroTitleLine2': 'agent-executable skills',
    'home.heroDesc': 'Upload EPUB files. AI analyzes the method structure deeply and creates a skills.zip package installable in Claude / Cursor.',
    'home.drop.active': 'Release to upload',
    'home.drop.idle': 'Drag or click to upload',
    'home.drop.hint': 'Supports EPUB, up to 50 MB',
    'home.processing.title': 'Parsing book structure',
    'home.processing.desc': 'Extracting chapters · Building semantic index · About 1-2 minutes',
    'home.ready.title': 'Parsing complete',
    'home.ready.generate': 'Generate skills.zip',
    'home.generating.title': 'Extracting methodology',
    'home.generating.desc': 'Generating SKILL.md · Building references/ · Packaging skill',
    'home.feature.grounded.label': 'Grounded',
    'home.feature.grounded.desc': 'Each output cites original text',
    'home.feature.refine.label': 'Refine by Chat',
    'home.feature.refine.desc': 'Iterate with natural language',
    'home.feature.install.label': 'Ready to Install',
    'home.feature.install.desc': 'Claude · Cursor · Custom Agents',
    'home.error.processFailed': 'Processing failed',
    'home.error.uploadFailed': 'Upload failed',
    'home.error.generateFailed': 'Generation failed',
    'library.uploadNewBook': 'Upload Book',
    'library.title': 'Library',
    'library.summary': '{total} books · {ready} processed',
    'library.loading': 'Loading',
    'library.loadFailed': 'Failed to load library. Please check backend connection.',
    'library.empty': 'No books uploaded yet',
    'library.uploadFirst': 'Upload your first book',
    'library.chatWithBook': 'Chat',
    'library.viewSkill': 'View Skill',
    'library.generateSkill': 'Generate Skill',
    'library.retrying': 'Retrying',
    'library.retry': 'Regenerate',
    'library.error.regenerateFailed': 'Regeneration failed',
    'library.status.pending': 'Pending',
    'library.status.processing': 'Processing',
    'library.status.ready': 'Ready',
    'library.status.error': 'Failed',
    'library.skill.generating': 'Skill generating',
    'library.skill.ready': 'Skill ready',
    'library.skill.error': 'Skill failed',
    'collections.title': 'Collections',
    'collections.librarySection': 'Collections',
    'collections.allTitle': 'All Collections',
    'collections.new': 'New Collection',
    'collections.viewAll': 'View all',
    'collections.create': 'Create Collection',
    'collections.name': 'Collection name',
    'collections.description': 'Description',
    'collections.selectBooks': 'Select books',
    'collections.readyBooksOnly': 'Only processed books can be selected',
    'collections.selectedCount': '{count} selected',
    'collections.createFailed': 'Failed to create collection',
    'collections.loadFailed': 'Failed to load collection',
    'collections.empty': 'No collections yet',
    'collections.bookCount': '{count} books',
    'collections.generateComingSoon': 'Collection skill generation opens in the next phase',
    'collections.sourceBooks': 'Source books',
    'collections.generate': 'Generate Skill',
    'collections.generating': 'Generating',
    'collections.userGoal': 'Generation goal',
    'collections.userGoalPlaceholder': 'Example: fit early-stage teams validating demand',
    'collections.generateFailed': 'Failed to generate collection skill',
    'chat.bookLoading': 'Loading...',
    'chat.semanticLoaded': 'Semantic index is loaded',
    'chat.mode.rag.title': 'Book Q&A',
    'chat.mode.rag.desc': 'Answers are grounded in vector retrieval with source citations to reduce hallucinations.',
    'chat.mode.agent.title': 'Skill Simulation',
    'chat.mode.agent.desc': 'Loads SKILL.md and applies extracted methodology to real-world scenarios.',
    'chat.empty.rag.title': 'Ask grounded questions',
    'chat.empty.agent.title': 'Start simulation mode',
    'chat.empty.rag.desc': 'Ask about key terms, logic relations, or chapter details and AI will answer with precise source grounding.',
    'chat.empty.agent.desc': 'Describe a real-world challenge and see how AI applies the extracted framework to solve it.',
    'chat.input.rag': 'Ask about the book...',
    'chat.input.agent': 'Describe your scenario and request guidance...',
    'chat.source.title': 'Source Evidence',
    'chat.source.count': 'Grounded in {count} source passages',
    'chat.error.answerFailed': 'Failed to answer: {message}',
    'chat.error.agentNoSkill': 'No skill package found yet. Please generate one to enable simulation mode.',
    'chat.error.refineException': '[Simulation exception] {message}',
    'chat.thinking.rag.1': 'Retrieving passages',
    'chat.thinking.rag.2': 'Matching vectors',
    'chat.thinking.rag.3': 'Building context',
    'chat.thinking.rag.4': 'Composing answer',
    'chat.thinking.agent.1': 'Loading skill package',
    'chat.thinking.agent.2': 'Analyzing scenario',
    'chat.thinking.agent.3': 'Simulating approach',
    'chat.thinking.agent.4': 'Generating suggestions',
    'skill.initAssets': 'Initializing assets...',
    'skill.title': 'Skill Package',
    'skill.versionReady': 'Version v{version} · Ready',
    'skill.versionBuilding': 'Version v{version} · Building',
    'skill.regenerate': 'Regenerate',
    'skill.packing': 'Packaging',
    'skill.exportZip': 'Export ZIP',
    'skill.downloadZip': 'Download ZIP',
    'skill.preview': 'SKILL.md Preview',
    'skill.generatingTitle': 'Extracting workflow',
    'skill.generatingDesc': 'AI is deeply parsing semantics and structuring the skill definition',
    'skill.emptyDefinition': '(No valid definition generated yet)',
    'skill.refineTitle': 'Refine by Chat',
    'skill.refineDesc': 'Fine-tune the skill definition by chatting. Ask AI to focus on specific chapters or adjust output style.',
    'skill.refinePlaceholder': 'Example: "Add more references for chapter 3 formulas"',
    'skill.refining': 'Updating...',
    'skill.updateDefinition': 'Update Definition',
    'skill.error.loadFailed': 'Failed to load skill',
    'skill.error.packFailed': 'Packaging failed',
    'skill.error.regenerateFailed': 'Regeneration failed',
    'skill.error.refineFailed': 'Refinement failed',
    'skill.partialWarningTitle': 'Some modules failed to generate',
    'skill.partialWarningDesc': 'Generated {generated}/{total} modules in this run; {failed} failed and were skipped. The current package is still usable.',
    'skill.regenerateConfirm': 'Regenerating will create a brand new skill package record. Continue?',
  },
}

function interpolate(template: string, params?: Params): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? ''))
}

function inferInitialLocale(): Locale {
  if (typeof window === 'undefined') return 'zh'
  const saved = window.localStorage.getItem(LOCALE_STORAGE_KEY)
  if (saved === 'zh' || saved === 'en') return saved
  const browserLocale = window.navigator.language.toLowerCase()
  return browserLocale.startsWith('zh') ? 'zh' : 'en'
}

type I18nContextValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (key: string, params?: Params) => string
}

const I18nContext = createContext<I18nContextValue | null>(null)

function persistLocale(locale: Locale) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  document.cookie = `${LOCALE_COOKIE_KEY}=${locale}; path=/; max-age=31536000; samesite=lax`
  document.documentElement.lang = locale === 'zh' ? 'zh-CN' : 'en'
}

export function LanguageProvider({
  children,
  initialLocale = 'zh',
}: {
  children: React.ReactNode
  initialLocale?: Locale
}) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale)

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale)
    // Persist immediately so navigation right after toggle keeps locale on SSR.
    persistLocale(nextLocale)
  }, [])

  useEffect(() => {
    const next = inferInitialLocale()
    setLocaleState(next)
    persistLocale(next)
  }, [])

  const t = useCallback((key: string, params?: Params) => {
    const dict = dictionaries[locale] ?? dictionaries.zh
    const fallback = dictionaries.zh[key] ?? key
    return interpolate(dict[key] ?? fallback, params)
  }, [locale])

  const value = useMemo<I18nContextValue>(() => ({
    locale,
    setLocale,
    t,
  }), [locale, t])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const context = useContext(I18nContext)
  if (!context) {
    throw new Error('useI18n must be used within LanguageProvider')
  }
  return context
}
