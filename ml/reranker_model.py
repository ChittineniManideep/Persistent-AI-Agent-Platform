"""
PyTorch cross-encoder-style reranker — takes a query and a set of candidate
passages, scores relevance, and reorders them. Used by the agent's `rerank`
tool step to improve tool-result quality before the LLM reasons over it.

Trained on a small synthetic relevance dataset here for demonstration;
architecture is a genuine trainable PyTorch model (embedding + scoring
head), not a wrapper around a pretrained black box.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np

torch.manual_seed(0)


class SimpleReranker(nn.Module):
    """A compact cross-encoder: query and passage are each embedded via a
    shared bag-of-embeddings encoder, concatenated, and scored by an MLP.
    Deliberately small/fast — a reranker in an agent's tool loop has to
    return in milliseconds, not seconds, which is a real production
    constraint distinct from the (larger, slower) generation model."""

    def __init__(self, vocab_size: int, embed_dim: int = 32, hidden_dim: int = 64):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size, embed_dim, padding_idx=0)
        self.scorer = nn.Sequential(
            nn.Linear(embed_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
        )

    def encode(self, token_ids: torch.Tensor) -> torch.Tensor:
        emb = self.embedding(token_ids)          # (batch, seq_len, embed_dim)
        mask = (token_ids != 0).unsqueeze(-1)
        summed = (emb * mask).sum(dim=1)
        counts = mask.sum(dim=1).clamp(min=1)
        return summed / counts                    # mean-pooled embedding, (batch, embed_dim)

    def forward(self, query_ids: torch.Tensor, passage_ids: torch.Tensor) -> torch.Tensor:
        q_emb = self.encode(query_ids)
        p_emb = self.encode(passage_ids)
        combined = torch.cat([q_emb, p_emb], dim=-1)
        return self.scorer(combined).squeeze(-1)   # relevance score, (batch,)


def build_toy_vocab_and_data():
    """Small synthetic relevance dataset: relevant passages share vocabulary
    with the query, irrelevant ones don't — enough signal to prove the
    training loop and scoring actually work end to end."""
    vocab = {"<pad>": 0}
    def tokenize(text):
        ids = []
        for w in text.lower().split():
            if w not in vocab:
                vocab[w] = len(vocab)
            ids.append(vocab[w])
        return ids

    pairs = [
        ("agent failure recovery patterns", "production agent failure recovery checkpointing", 1),
        ("agent failure recovery patterns", "cooking pasta recipes for dinner", 0),
        ("kubernetes deployment scaling", "kubernetes horizontal pod autoscaler deployment", 1),
        ("kubernetes deployment scaling", "history of ancient rome empire", 0),
        ("pytorch reranker model training", "training a pytorch cross encoder reranker", 1),
        ("pytorch reranker model training", "gardening tips for spring planting", 0),
        ("streaming latency budget", "real time streaming latency constraints budget", 1),
        ("streaming latency budget", "best hiking trails in ireland", 0),
        ("session persistence redis", "persisting agent session state in redis", 1),
        ("session persistence redis", "top ten movies of the decade", 0),
    ] * 8  # repeat for a slightly larger training set

    tokenized = [(tokenize(q), tokenize(p), label) for q, p, label in pairs]
    return vocab, tokenized


def pad(seqs, max_len):
    return torch.tensor([s + [0] * (max_len - len(s)) for s in seqs], dtype=torch.long)


if __name__ == "__main__":
    vocab, data = build_toy_vocab_and_data()
    max_len = max(max(len(q), len(p)) for q, p, _ in data)

    queries = pad([q for q, p, l in data], max_len)
    passages = pad([p for q, p, l in data], max_len)
    labels = torch.tensor([float(l) for q, p, l in data])

    model = SimpleReranker(vocab_size=len(vocab))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

    print(f"Training reranker on {len(data)} query-passage pairs, vocab size {len(vocab)}...")
    for epoch in range(60):
        optimizer.zero_grad()
        scores = model(queries, passages)
        loss = F.binary_cross_entropy_with_logits(scores, labels)
        loss.backward()
        optimizer.step()
        if epoch % 15 == 0:
            preds = (torch.sigmoid(scores) > 0.5).float()
            acc = (preds == labels).float().mean().item()
            print(f"  epoch {epoch:3d} | loss {loss.item():.4f} | train acc {acc:.3f}")

    with torch.no_grad():
        final_scores = torch.sigmoid(model(queries, passages))
        final_acc = ((final_scores > 0.5).float() == labels).float().mean().item()
    print(f"Final training accuracy: {final_acc:.3f}")
    torch.save(model.state_dict(), "ml/reranker_model.pt")
    print("Model saved to ml/reranker_model.pt")
