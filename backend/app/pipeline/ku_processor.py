import asyncio
import logging

import hdbscan
import numpy as np
import umap
from sklearn.metrics.pairwise import cosine_similarity

from app.core.llm import get_embedding_client
from app.schemas.schemas import KnowledgeUnit

logger = logging.getLogger(__name__)

class KUProcessor:
    """
    负责对提取出的 KnowledgeUnits (KUs) 进行数学运算处理。
    1. 去重 (Deduplication)
    2. 降维 (UMAP)
    3. 聚类 (HDBSCAN)
    """

    def __init__(self):
        self.embedder = get_embedding_client()

    async def _embed_one(self, text: str, semaphore: asyncio.Semaphore) -> list:
        """单条原文 Embedding，带并发信号量控制"""
        async with semaphore:
            return await self.embedder.aembed_query(text)

    async def _get_embeddings(self, texts: list[str], chunk_size: int = 100) -> np.ndarray:
        """批量获取文本的向量表示"""
        embeddings = []
        for i in range(0, len(texts), chunk_size):
            batch_texts = texts[i:i + chunk_size]
            # 兼容处理
            if hasattr(self.embedder, "aembed_documents"):
                batch_embs = await self.embedder.aembed_documents(batch_texts)
            else:
                # 修复：使用 Semaphore 控制并发，防止触发 API Rate Limit (Suggestion 1)
                sem = asyncio.Semaphore(10)
                tasks = [self._embed_one(t, sem) for t in batch_texts]
                batch_embs = await asyncio.gather(*tasks)
            embeddings.extend(batch_embs)
        return np.array(embeddings)

    def deduplicate_kus(self, kus: list[KnowledgeUnit], embeddings: np.ndarray, threshold: float = 0.92) -> tuple[list[KnowledgeUnit], np.ndarray]:
        """
        基于余弦相似度去除高度重复的 KU
        - threshold: 相似度阈值，大于该值认为是重复内容
        - 优先保留文本更长的 KU
        """
        if not kus or len(kus) <= 1:
            return kus, embeddings

        logger.info(f"Starting deduplication for {len(kus)} KUs with threshold {threshold}...")

        # 计算相似度矩阵
        sim_matrix = cosine_similarity(embeddings)
        n = len(kus)

        # 记录被保留的索引
        keep_indices = set(range(n))

        # 遍历交叉匹配寻找重复对
        for i in range(n):
            if i not in keep_indices:
                continue

            removed_i = False # 修复：使用标志位明确控制外层循环 (Suggestion 2)
            for j in range(i + 1, n):
                if j not in keep_indices:
                    continue

                if sim_matrix[i, j] > threshold:
                    # 发现高度相似的对，保留文本较长的一个
                    len_i = len(kus[i].principle or "") + len(kus[i].method or "") + len(str(kus[i].step_by_step))
                    len_j = len(kus[j].principle or "") + len(kus[j].method or "") + len(str(kus[j].step_by_step))

                    if len_i >= len_j:
                        keep_indices.remove(j)
                    else:
                        keep_indices.remove(i)
                        removed_i = True
                        break # 跳出内层循环，由 removed_i 标志和 continue 保护外层

            if removed_i:
                continue

        keep_idx_list = sorted(list(keep_indices))
        deduped_kus = [kus[i] for i in keep_idx_list]
        deduped_embeddings = embeddings[keep_idx_list]

        logger.info(f"Deduplication complete. Removed {n - len(deduped_kus)} duplicates. {len(deduped_kus)} remaining.")
        return deduped_kus, deduped_embeddings

    def cluster_kus_hdbscan(self, kus: list[KnowledgeUnit], embeddings: np.ndarray) -> list[tuple[int, list[KnowledgeUnit]]]:
        """
        使用 UMAP降维 + HDBSCAN 聚类 KUs
        """
        # 修复：小数据 fallback 阈值上调至 10 (Suggestion 4)
        if len(kus) < 10:
            logger.warning(f"Too few KUs ({len(kus)}) for HDBSCAN. Grouping all into one cluster.")
            return [(0, kus)]

        logger.info(f"Starting UMAP dimension reduction for {len(kus)} vectors...")

        # 1. UMAP 降维
        # 修复：调整 n_neighbors 公式，平衡局部与全局结构 (Suggestion 3)
        n_neighbors = min(50, max(5, int(np.sqrt(len(kus)))))

        try:
            reducer = umap.UMAP(
                n_neighbors=n_neighbors,
                n_components=10,
                metric='cosine',
                random_state=42
            )
            reduced_embeddings = reducer.fit_transform(embeddings)
            logger.info("UMAP completed.")
        except Exception as e:
            logger.error(f"UMAP failed, falling back to original embeddings: {e}")
            reduced_embeddings = embeddings

        # 2. HDBSCAN 聚类
        logger.info("Starting HDBSCAN clustering...")

        # 修复：改进 min_cluster_size 公式，确保随规模线性增长 (Suggestion 5)
        min_cluster_size = max(5, len(kus) // 50)

        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric='euclidean',
            cluster_selection_method='eom'
        )

        labels = clusterer.fit_predict(reduced_embeddings)

        # 3. 组织结果
        clusters_dict = {}
        noise_cluster_id = -1

        for k_idx, label in enumerate(labels):
            # 修复：不丢弃噪声点，标记为特殊杂项簇 (Suggestion 6)
            effective_label = label if label != -1 else noise_cluster_id

            if effective_label not in clusters_dict:
                clusters_dict[effective_label] = []
            clusters_dict[effective_label].append(kus[k_idx])

        logger.info(f"HDBSCAN clustering complete. Found {len(clusters_dict)} clusters (including noise pool if any).")

        # 转为 Tuple 列表格式
        results = [(int(label), group) for label, group in clusters_dict.items()]
        return results

    async def process_and_cluster(self, kus: list[KnowledgeUnit]) -> list[tuple[int, list[KnowledgeUnit]]]:
        """主入口：向量化 -> 去重 -> 降维聚类"""
        if not kus:
            return []

        logger.info(f"Starting KU Processing pipeline for {len(kus)} KUs.")

        # 1. 准备要提取 embedding 的文本 (主干：原理与方法)
        texts = []
        for ku in kus:
            parts = []
            if ku.principle:
                parts.append(ku.principle)
            if ku.method:
                parts.append(ku.method)
            # 如果两者都空，尝试用 step_by_step 拼接凑救命文本
            if not parts and ku.step_by_step:
                parts.append("; ".join(ku.step_by_step))
            text = " ".join(parts) if parts else "Unknown Concept"
            texts.append(text)

        # 2. 获取向量
        logger.info("Fetching embeddings from LLM service...")
        embeddings = await self._get_embeddings(texts)

        # 3. 去重
        deduped_kus, deduped_embeddings = self.deduplicate_kus(kus, embeddings)

        # 4. 聚类
        clustered_groups = self.cluster_kus_hdbscan(deduped_kus, deduped_embeddings)

        return clustered_groups
