import hashlib
import re

import numpy as np
import pytest

from secondbrain.engine import Brain


class TestEmbeddings:
    """Deterministic test double; not used by the application."""
    def text(self, texts, query=False):
        output = []
        for text in texts:
            vector = np.zeros(128, dtype=np.float32)
            for word in re.findall(r'\w+', text.lower()):
                vector[int.from_bytes(hashlib.sha256(word.encode()).digest()[:2], 'big') % 128] += 1
            output.append(vector)
        return output

    def image(self, path):
        return np.ones(32, dtype=np.float32)

    def visual_query(self, text):
        return np.ones(32, dtype=np.float32)


@pytest.fixture
def brain(tmp_path):
    brain = Brain(tmp_path / 'collection', embeddings=TestEmbeddings())
    brain.workspace.settings.vision = False
    brain.workspace.settings.ocr = False
    return brain
