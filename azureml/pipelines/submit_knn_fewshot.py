import time

from dataclasses import dataclass

import hydra
from hydra.core.config_store import ConfigStore

import omegaconf

from azure.identity import DefaultAzureCredential
from azure.ai.ml import MLClient

from azure.ai.ml import dsl, MLClient, Input
from azure.ai.ml.entities import Pipeline

from azureml_utils import get_component_collector, ComponentCollector
from configs import AMLConfig, KNNFewshotConfig, AOAIConfig
from logging_utils import get_standard_logger_for_file

_logger = get_standard_logger_for_file(__file__)


@dataclass
class PipelineConfig:
    knn_fewshot_config: KNNFewshotConfig = omegaconf.MISSING
    azureml_config: AMLConfig = omegaconf.MISSING
    aoai_config: AOAIConfig = omegaconf.MISSING
    aoai_embedding_config: AOAIConfig = omegaconf.MISSING


cs = ConfigStore.instance()
cs.store(name="config", node=PipelineConfig)


def create_embedding_for_split_pipeline(
    components: ComponentCollector,
    mmlu_folder: Input,
    target_split: str,
    embedding_output_key: str,
    aoai_embedding_config: AOAIConfig,
):
    question_key = "question"

    @dsl.pipeline(
        name=f"extract_embeddings_{target_split}",
        display_name=f"extract_embeddings_{target_split}",
    )
    def extract_embeddings(mmlu_dir: Input):
        get_split_job = components.uri_folder_to_file(
            input_dataset=mmlu_dir,
            filename_pattern=f"{target_split}.jsonl",
        )
        get_split_job.name = f"extract_split_{target_split}"

        embedding_job = components.jsonl_embeddings(
            input_dataset=get_split_job.outputs.output_dataset,
            source_key=question_key,
            destination_key=embedding_output_key,
            workers=aoai_embedding_config.workers,
            max_errors=aoai_embedding_config.max_errors,
            azure_openai_endpoint=aoai_embedding_config.endpoint,
        )
        embedding_job.compute = aoai_embedding_config.compute_target
        embedding_job.name = f"add_embeddings_{target_split}"

        return {"output_dataset": embedding_job.outputs.output_dataset}

    sub_pipeline = extract_embeddings(mmlu_folder)

    return sub_pipeline.outputs.output_dataset


def create_knn_fewshot_pipeline(
    ml_client: MLClient, run_config: KNNFewshotConfig, version_string: str
):
    components = get_component_collector(ml_client, version_string)

    embeddings_key = "question_embedding"

    @dsl.pipeline()
    def basic_pipeline() -> Pipeline:
        mmlu_fetch_job = components.jsonl_mmlu_fetch(
            mmlu_dataset=run_config.mmlu_dataset
        )
        mmlu_fetch_job.name = f"fetch_mmlu_{run_config.mmlu_dataset}"

        test_with_embeddings = create_embedding_for_split_pipeline(
            components,
            mmlu_fetch_job.outputs.output_dataset,
            target_split=run_config.test_split,
            embedding_output_key=embeddings_key,
            aoai_embedding_config=run_config.aoai_embedding_config,
        )

        examples_with_embeddings = create_embedding_for_split_pipeline(
            components,
            mmlu_fetch_job.outputs.output_dataset,
            target_split=run_config.example_split,
            embedding_output_key=embeddings_key,
            aoai_embedding_config=run_config.aoai_embedding_config,
        )

    pipeline = basic_pipeline()
    pipeline.experiment_name = (
        f"{run_config.pipeline.base_experiment_name}_{run_config.mmlu_dataset}"
    )
    pipeline.display_name = None
    pipeline.compute = run_config.pipeline.default_compute_target
    if run_config.pipeline.tags:
        pipeline.tags.update(run_config.tags)
    _logger.info("Pipeline created")

    return pipeline


@hydra.main(config_path="configs", version_base="1.1")
def main(config: PipelineConfig):
    version_string = str(int(time.time()))
    _logger.info(f"AzureML object version for this run: {version_string}")

    _logger.info(f"Azure Subscription: {config.azureml_config.subscription_id}")
    _logger.info(f"Resource Group: {config.azureml_config.resource_group}")
    _logger.info(f"Workspace : {config.azureml_config.workspace_name}")

    credential = DefaultAzureCredential(exclude_shared_token_cache_credential=True)

    ws_client = MLClient(
        credential=credential,
        subscription_id=config.azureml_config.subscription_id,
        resource_group_name=config.azureml_config.resource_group,
        workspace_name=config.azureml_config.workspace_name,
        logging_enable=False,
    )

    pipeline = create_knn_fewshot_pipeline(
        ws_client, config.knn_fewshot_config, version_string
    )
    _logger.info("Submitting pipeline")
    submitted_job = ws_client.jobs.create_or_update(pipeline)
    _logger.info(f"Submitted: {submitted_job.name}")


if __name__ == "__main__":
    main()