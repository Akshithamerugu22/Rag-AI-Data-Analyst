import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer


class RAGEngine:
    """
    FAISS-based RAG engine for the Universal AI Data Analyst.

    Supports:
        rag.add_documents(documents)
        rag.add_documents(source, documents)

    Flow:
        Documents
            ↓
        Embeddings
            ↓
        FAISS
            ↓
        Similarity Search
            ↓
        Relevant Context
    """

    def __init__(self):

        # ---------------------------------------------------------
        # 1. Embedding model
        # ---------------------------------------------------------
        model_name = os.getenv(
            "EMBEDDING_MODEL",
            "all-MiniLM-L6-v2"
        )

        self.model = SentenceTransformer(model_name)

        # ---------------------------------------------------------
        # 2. Embedding dimension
        # ---------------------------------------------------------
        self.dimension = self.model.get_embedding_dimension()

        # ---------------------------------------------------------
        # 3. FAISS index
        # ---------------------------------------------------------
        self.index = faiss.IndexFlatL2(
            self.dimension
        )

        # ---------------------------------------------------------
        # 4. Stored documents
        # ---------------------------------------------------------
        self.documents = []

        # ---------------------------------------------------------
        # 5. Optional source information
        # ---------------------------------------------------------
        self.sources = []

    # =============================================================
    # ADD DOCUMENTS
    # =============================================================
    def add_documents(self, *args):
        """
        Add documents to the FAISS vector database.

        Supported:

            add_documents(documents)

        OR:

            add_documents(source, documents)
        """

        # ---------------------------------------------------------
        # Handle arguments
        # ---------------------------------------------------------

        if len(args) == 1:

            source = "unknown"

            documents = args[0]

        elif len(args) == 2:

            source = args[0]

            documents = args[1]

        else:

            raise TypeError(
                "add_documents() expects either "
                "documents or source, documents"
            )

        # ---------------------------------------------------------
        # Check documents
        # ---------------------------------------------------------

        if not documents:
            return

        texts = []
        document_sources = []

        # ---------------------------------------------------------
        # Process every document
        # ---------------------------------------------------------

        for document in documents:

            # Dictionary document
            if isinstance(document, dict):

                text = document.get(
                    "text",
                    ""
                )

                # Allow individual document source
                document_source = document.get(
                    "source",
                    source
                )

            # Plain text document
            else:

                text = str(document)

                document_source = source

            # -----------------------------------------------------
            # Ignore empty text
            # -----------------------------------------------------

            if not text:
                continue

            if not text.strip():
                continue

            text = text.strip()

            # -----------------------------------------------------
            # Save
            # -----------------------------------------------------

            texts.append(text)

            document_sources.append(
                str(document_source)
            )

        # ---------------------------------------------------------
        # Nothing to add
        # ---------------------------------------------------------

        if not texts:
            return

        # ---------------------------------------------------------
        # Generate embeddings
        # ---------------------------------------------------------

        embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        embeddings = np.asarray(
            embeddings,
            dtype=np.float32
        )

        # ---------------------------------------------------------
        # Add to FAISS
        # ---------------------------------------------------------

        self.index.add(
            embeddings
        )

        # ---------------------------------------------------------
        # Store documents
        # ---------------------------------------------------------

        self.documents.extend(
            texts
        )

        self.sources.extend(
            document_sources
        )

    # =============================================================
    # SEARCH
    # =============================================================
    def search(
        self,
        query,
        top_k=5
    ):
        """
        Search the vector database.

        Returns a list of relevant document texts.
        """

        if not query:
            return []

        if self.index.ntotal == 0:
            return []

        # Make sure top_k isn't larger
        # than the number of stored documents.

        top_k = min(
            top_k,
            self.index.ntotal
        )

        # ---------------------------------------------------------
        # Query embedding
        # ---------------------------------------------------------

        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        query_embedding = np.asarray(
            query_embedding,
            dtype=np.float32
        )

        # ---------------------------------------------------------
        # FAISS search
        # ---------------------------------------------------------

        distances, indices = self.index.search(
            query_embedding,
            top_k
        )

        results = []

        # ---------------------------------------------------------
        # Collect results
        # ---------------------------------------------------------

        for index in indices[0]:

            if index == -1:
                continue

            if index >= len(
                self.documents
            ):
                continue

            results.append(
                self.documents[index]
            )

        return results

    # =============================================================
    # SEARCH WITH SOURCE
    # =============================================================
    def search_with_sources(
        self,
        query,
        top_k=5
    ):
        """
        Search and return documents together
        with their source information.
        """

        if not query:
            return []

        if self.index.ntotal == 0:
            return []

        top_k = min(
            top_k,
            self.index.ntotal
        )

        query_embedding = self.model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False
        )

        query_embedding = np.asarray(
            query_embedding,
            dtype=np.float32
        )

        distances, indices = self.index.search(
            query_embedding,
            top_k
        )

        results = []

        for index, distance in zip(
            indices[0],
            distances[0]
        ):

            if index == -1:
                continue

            if index >= len(
                self.documents
            ):
                continue

            results.append(
                {
                    "text": self.documents[index],
                    "source": (
                        self.sources[index]
                        if index < len(self.sources)
                        else "unknown"
                    ),
                    "distance": float(distance)
                }
            )

        return results

    # =============================================================
    # CLEAR
    # =============================================================
    def clear(self):

        self.index = faiss.IndexFlatL2(
            self.dimension
        )

        self.documents = []

        self.sources = []

    # =============================================================
    # RESET
    # =============================================================
    def reset(self):
        """
        Reset the RAG engine.

        app.py uses:
            rag.reset()
        """

        self.clear()

    # =============================================================
    # COUNT
    # =============================================================
    def count(self):

        return self.index.ntotal