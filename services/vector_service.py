import logging
from pymilvus import Collection
from core.messages import ServerMessages

logger = logging.getLogger("uvicorn.error")


def milvus_search(col: str, metric_type: str, nprobe: int, embedded_data: list, top_k: int, output_fields: list):
    """Perform a vector similarity search in Milvus.

    Args:
        col (str): Name of the Milvus collection.
        metric_type (str): Similarity metric type.
        nprobe (int): Number of probes for search accuracy.
        embedded_data (list): Query embedding vectors.
        top_k (int): Number of top results to return.
        output_fields (list): Fields to include in the search result.

    Returns:
        list: Milvus search results, or an empty list if an error occurs.
    """
    try:
        search_params = {
            "metric_type": metric_type,
            "params": {"nprobe": nprobe}
        }

        collection = Collection(col)
        results = collection.search(
            data=embedded_data,
            anns_field="embedding",
            param=search_params,
            limit=top_k,
            output_fields=output_fields
        )
        return results
    except Exception as e:
        logger.error(ServerMessages.MILVUS_SEARCH_ERROR + f"{e}")
        return []
