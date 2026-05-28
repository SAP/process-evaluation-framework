import os
from sentence_transformers import SentenceTransformer, util


# Model selection: ungated default + opt-in upgrade path via env var.
DEFAULT_MODEL = 'Alibaba-NLP/gte-large-en-v1.5'
MODEL_NAME = os.environ.get("SIMILARITY_MODEL", DEFAULT_MODEL)
# model = SentenceTransformer('Alibaba-NLP/gte-large-en-v1.5', trust_remote_code=True)

# EmbeddingGemma was trained with task-specific prompts; the "STS" prompt
# is the right one for symmetric similarity (BPMN-name ↔ BPMN-name).
# Other sentence-transformers models in this slot work fine without a prompt.
_USES_STS_PROMPT = False #MODEL_NAME

model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)

cache = {}


def cosine_sim_optimized(t1, t2):
    """Cosine similarity between two strings, with an embedding cache.

    Encoding is the expensive part. During BPMN normalization the same
    string is re-queried many times across pairwise comparisons, so caching
    embeddings reduces wall-clock from minutes to seconds.

    Args:
        t1, t2: Strings to compare.

    Returns:
        Cosine similarity in [-1, 1] as a Python float.
    """
    def encode(value):
        hit = cache.get(value)
        if hit is not None:
            return hit
        if _USES_STS_PROMPT:
            embedding = model.encode(value, prompt_name="STS", convert_to_tensor=True)
        else:
            embedding = model.encode(value, convert_to_tensor=True)
        cache[value] = embedding
        return embedding

    score = util.pytorch_cos_sim(encode(t1), encode(t2))
    return score.item()