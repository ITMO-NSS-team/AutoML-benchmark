import datetime
import gc
import os

import numpy as np
from pathlib import Path

from experiments.credit_scoring_experiment import run_credit_scoring_problem
from experiments.gp_schemes_experiment import write_header_to_csv, add_result_to_csv, \
    results_preprocess_and_quality_visualisation
from experiments.viz import viz_pareto_fronts_comparison, viz_hv_comparison

from fedot.core.composer.optimisers.crossover import CrossoverTypesEnum
from fedot.core.composer.optimisers.inheritance import GeneticSchemeTypesEnum
from fedot.core.composer.optimisers.gp_optimiser import GPChainOptimiserParameters
from fedot.core.composer.optimisers.mutation import MutationTypesEnum
from fedot.core.composer.optimisers.regularization import RegularizationTypesEnum
from fedot.core.composer.optimisers.selection import SelectionTypesEnum
from fedot.core.composer.optimisers.multi_objective_fitness import MultiObjFitness
from fedot.core.repository.quality_metrics_repository import ClassificationMetricsEnum, ComplexityMetricsEnum, \
    MetricsRepository, RegressionMetricsEnum
from fedot.core.repository.tasks import TaskTypesEnum, Task

all_results_chains_file = 'all_result_chains.csv'


def proj_root():
    return Path(__file__).parent.parent


def save_composer_history(experiment_path: str,
                          name_of_experiment: str,
                          metrics: list,
                          chains: list,
                          history_save_flag: bool = False):
    metric_save = os.path.join(str(experiment_path), name_of_experiment + '_best_metric')
    chain_save = os.path.join(str(experiment_path), name_of_experiment + '_best_chains')
    if history_save_flag:
        metric_save = os.path.join(str(experiment_path), name_of_experiment + '_history_of_quality')
        chain_save = os.path.join(str(experiment_path), name_of_experiment + '_history_of_individuals')
    np.save(metric_save, metrics, allow_pickle=True)
    np.save(chain_save, chains, allow_pickle=True)
    return


def extract_quality_list(task, pop):
    if type(pop[0].fitness) is MultiObjFitness:
        return [-ind.fitness.values[0] if task.task_type == TaskTypesEnum.classification else
                ind.fitness.values[0] for ind in pop]
    else:
        return [-ind.fitness if task.task_type == TaskTypesEnum.classification else
                ind.fitness for ind in pop]


def run_multi_obj_exp(selection_types, history_file='history.csv', labels=None, genetic_schemes_set=None,
                      depth_config=None, iterations=30,
                      runs=1, pop_sizes=(20, 20, 20, 20), crossover_types=None, metrics=None, mutation_types=None,
                      regular_type=RegularizationTypesEnum.decremental, train_path=None, test_path=None,
                      name_of_dataset=None, visualize_pareto=False, visualize_hv=False,
                      objectives_names=('ROC-AUC metric', 'Computation time'), task=Task(TaskTypesEnum.classification)):
    max_amount_of_time = 800
    step = 800
    full_path_train = train_path
    full_path_test = test_path
    all_history = [[] for _ in range(len(labels))]
    file_path_best = name_of_dataset + '_multiobj_exp_best.csv'
    row = ['exp_number', 'exp_type', 'iteration', 'complexity', 't_opt', 'regular', 'AUC', 'n_models', 'n_layers']
    write_header_to_csv(file_path_best, row=row)
    time_amount = step
    if not metrics:
        metrics = [ClassificationMetricsEnum.ROCAUC, ComplexityMetricsEnum.computation_time]
    max_depths = [3, 3, 3, 3]
    start_depth = [2, 2, 2, 2]  # starting depth for 1st population initialization
    history_quality_gp = [[] for _ in range(len(labels))]
    inds_history_gp = [[] for _ in range(len(labels))]
    pareto_fronts_metrics = []
    n = 0
    while time_amount <= max_amount_of_time:
        for type_num, scheme_type in enumerate(genetic_schemes_set):
            for run in range(runs):
                n += 1
                gc.collect()
                if not crossover_types:
                    crossover_types = [CrossoverTypesEnum.one_point, CrossoverTypesEnum.subtree]
                if not mutation_types:
                    mutation_types = [MutationTypesEnum.simple, MutationTypesEnum.growth, MutationTypesEnum.reduce]
                genetic_scheme_type = scheme_type
                with_auto_depth_configuration = depth_config[type_num]
                max_depth_in_exp = max_depths[type_num]
                start_depth_in_exp = start_depth[type_num]

                if any([type(m) is list for m in metrics]):
                    metric = metrics[type_num]
                else:
                    metric = metrics
                selection_type = selection_types[type_num]
                optimiser_parameters = GPChainOptimiserParameters(selection_types=selection_type,
                                                                  crossover_types=crossover_types,
                                                                  mutation_types=mutation_types,
                                                                  regularization_type=regular_type,
                                                                  genetic_scheme_type=genetic_scheme_type,
                                                                  with_auto_depth_configuration=
                                                                  with_auto_depth_configuration)

                calculated_metrics, chains, composer = run_credit_scoring_problem(full_path_train, full_path_test,
                                                                                  max_lead_time=datetime.timedelta(
                                                                                      minutes=time_amount),
                                                                                  gp_optimiser_params=optimiser_parameters,
                                                                                  pop_size=pop_sizes[type_num],
                                                                                  generations=iterations,
                                                                                  max_depth=max_depth_in_exp,
                                                                                  start_depth=start_depth_in_exp,
                                                                                  metrics=metric, task=task)

                is_regular = regular_type == RegularizationTypesEnum.decremental
                all_history[type_num].append(composer)
                try:
                    tmp_folder = str(run + 1) + '_experiment'
                    experiment_path = f'D:\результаты экспериментов\{name_of_dataset}\{tmp_folder}'
                    if not os.path.isdir(experiment_path):
                        os.makedirs(experiment_path)
                    name_of_experiment = name_of_dataset + '_' + labels[type_num] + '_run_number_' + str(run + 1)
                    save_composer_history(experiment_path, name_of_experiment, calculated_metrics, chains, composer)
                except Exception as ex:
                    print(ex)

                if type(metric) is list:
                    roc_auc_metrics = calculated_metrics[0]
                    complexity_metrics = calculated_metrics[1]
                else:
                    roc_auc_metrics = calculated_metrics

                if visualize_pareto:
                    archive_len = len(composer.history.archive_history)
                    pareto_front = composer.history.archive_history[archive_len - 1]
                    quality_list = extract_quality_list(task=task, pop=pareto_front)
                    complexity_list = [ind.fitness.values[1] for ind in pareto_front]

                    pareto_fronts_metrics.append([quality_list, complexity_list])

                if type(metric) is list:
                    historical_quality = [
                        extract_quality_list(task=task, pop=pop) + extract_quality_list(task=task, pop=
                        composer.history.archive_history[i]) for i, pop in enumerate(composer.history.individuals)]
                    history_quality_gp[type_num].append(historical_quality)
                else:
                    historical_quality = [extract_quality_list(task=task, pop=pop) for pop in
                                          composer.history.individuals]
                    history_quality_gp[type_num].append(historical_quality)

                for i, roc_auc in enumerate(roc_auc_metrics):
                    if type(metric) is list:
                        compl = complexity_metrics[i]
                    else:
                        compl = MetricsRepository().metric_by_id(ComplexityMetricsEnum.computation_time)(chains[i])

                    add_result_to_csv(file_path_best, time_amount, is_regular, round(roc_auc, 4),
                                      len(chains[i].nodes),
                                      chains[i].depth, exp_type=labels[type_num], iteration=run,
                                      complexity=compl, exp_number=type_num)
                try:
                    experiment_path = f'D:\результаты экспериментов\{name_of_dataset}'
                    if not os.path.isdir(experiment_path):
                        os.makedirs(experiment_path)
                    name_of_experiment = name_of_dataset + '_' + labels[type_num] + '_run_number_' + str(run)
                    save_composer_history(experiment_path, name_of_experiment, history_quality_gp, inds_history_gp,
                                          history_save_flag=True)

                except Exception as ex:
                    print(ex)

        time_amount += step

    if runs > 1:
        quality_label = 'ROC-AUC' if task.task_type == TaskTypesEnum.classification else 'RMSE'
        xy_labels = ('Generation, #', f'Best {quality_label}')
        results_preprocess_and_quality_visualisation(history_gp=history_quality_gp, labels=labels,
                                                     iterations=iterations, name_of_dataset=name_of_dataset, task=task,
                                                     xy_labels=xy_labels)
    if visualize_pareto:
        if runs == 1:
            pareto_metrics = pareto_fronts_metrics
        else:
            pareto_metrics = [pareto_fronts_metrics[i] for i in range(0, len(pareto_fronts_metrics), runs)]

        viz_pareto_fronts_comparison(pareto_metrics, labels=labels, name_of_dataset=name_of_dataset,
                                     objectives_names=objectives_names)
        try:
            path_to_save_pareto = name_of_dataset + '_pareto_set_gp'
            np.save(path_to_save_pareto, pareto_metrics)
        except Exception as ex:
            print(ex)
    if visualize_hv:
        viz_hv_comparison(labels=labels, all_history_report=all_history, name_of_dataset=name_of_dataset,
                          iterations=iterations)


def exp_self_config_vs_fix_params(train_path: str,
                                  test_path: str,
                                  name_of_dataset: str, task: Task):
    history_file = name_of_dataset + '_history_selfconf_vs_fixparams.csv'
    genetic_schemes_set = [GeneticSchemeTypesEnum.parameter_free, GeneticSchemeTypesEnum.parameter_free,
                           GeneticSchemeTypesEnum.steady_state, GeneticSchemeTypesEnum.steady_state]
    depth_config_option = [False, True, False, True]  # depth configuration option (Active/No active)
    labels = []
    for i in range(len(genetic_schemes_set)):
        depth_config_label = ' with fixed max_depth'
        if depth_config_option[i]:
            depth_config_label = ''
        label = f'{genetic_schemes_set[i].value} GP' + depth_config_label
        labels.append(label)
    quality_metric = ClassificationMetricsEnum.ROCAUC
    if task.task_type == TaskTypesEnum.regression:
        quality_metric = RegressionMetricsEnum.RMSE
    metrics = [[quality_metric, ComplexityMetricsEnum.computation_time] for _ in range(len(labels))]
    multi_obj_sel = [SelectionTypesEnum.spea2]
    selection_types = [multi_obj_sel for _ in range(len(labels))]
    quality_metric_name = 'ROC-AUC metric' if task.task_type == TaskTypesEnum.classification else 'RMSE metric'
    objectives_names = (quality_metric_name, 'Computation time')
    run_multi_obj_exp(history_file=history_file, labels=labels, genetic_schemes_set=genetic_schemes_set, runs=3,
                      metrics=metrics, selection_types=selection_types, depth_config=depth_config_option,
                      visualize_pareto=True, visualize_hv=True, objectives_names=objectives_names,
                      train_path=train_path, test_path=test_path, name_of_dataset=name_of_dataset, task=task)


def exp_single_vs_multi_objective(train_path: str,
                                  test_path: str,
                                  name_of_dataset: str, task: Task):
    history_file = name_of_dataset + '_history_single_vs_multiobj.csv'
    runs = 4
    genetic_schemes_set = [GeneticSchemeTypesEnum.steady_state for _ in range(3)]
    scheme_label = genetic_schemes_set[0].value
    labels = [f'{scheme_label} single-obj GP', f'{scheme_label} single-obj penalty', f'{scheme_label} multi-obj']
    metrics = [ClassificationMetricsEnum.ROCAUC, ClassificationMetricsEnum.ROCAUC_penalty,
               [ClassificationMetricsEnum.ROCAUC, ComplexityMetricsEnum.structural]]
    if task.task_type == TaskTypesEnum.regression:
        metrics = [RegressionMetricsEnum.RMSE, RegressionMetricsEnum.RMSE_penalty,
                   [RegressionMetricsEnum.RMSE, ComplexityMetricsEnum.structural]]
    single_obj_sel = [SelectionTypesEnum.tournament]
    multi_obj_sel = [SelectionTypesEnum.spea2]
    selection_types = [single_obj_sel, single_obj_sel, multi_obj_sel]
    depth_config_option = [False, False, False, False]  # depth configuration option (Active/No active)
    quality_metric_name = 'ROC-AUC metric' if task.task_type == TaskTypesEnum.classification else 'RMSE metric'
    objectives_names = (quality_metric_name, 'Computation time')
    run_multi_obj_exp(history_file=history_file, labels=labels, genetic_schemes_set=genetic_schemes_set, runs=runs,
                      metrics=metrics, selection_types=selection_types, depth_config=depth_config_option,
                      train_path=train_path, test_path=test_path, name_of_dataset=name_of_dataset, task=task,
                      objectives_names=objectives_names)


def exp_multi_obj_selections(train_path: str,
                             test_path: str,
                             name_of_dataset: str, task: Task):
    history_file = name_of_dataset + '_history_selfconf_vs_fixparams.csv'
    genetic_schemes_set = [GeneticSchemeTypesEnum.parameter_free, GeneticSchemeTypesEnum.parameter_free]
    scheme_label = genetic_schemes_set[0].value
    labels = [f'{scheme_label} GP with nsga selection', f'{scheme_label} GP with spea2 selection']
    quality_metric = ClassificationMetricsEnum.ROCAUC
    if task.task_type == TaskTypesEnum.regression:
        quality_metric = RegressionMetricsEnum.RMSE
    metrics = [[quality_metric, ComplexityMetricsEnum.computation_time] for _ in range(len(labels))]
    selection_types = [[SelectionTypesEnum.nsga2], [SelectionTypesEnum.spea2]]
    depth_config_option = [False, False]  # depth configuration option (Active/No active)
    run_multi_obj_exp(history_file=history_file, labels=labels, genetic_schemes_set=genetic_schemes_set, runs=4,
                      metrics=metrics, selection_types=selection_types, depth_config=depth_config_option,
                      train_path=train_path, test_path=test_path, name_of_dataset=name_of_dataset,
                      visualize_pareto=True, task=task)


def exp_complexity_metrics(train_path: str,
                           test_path: str,
                           name_of_dataset: str, task: Task):
    history_file = name_of_dataset + '_history_selfconf_vs_fixparams.csv'
    labels = ['computation time', 'structural complexity']
    genetic_schemes_set = [GeneticSchemeTypesEnum.steady_state, GeneticSchemeTypesEnum.steady_state]
    quality_metric = ClassificationMetricsEnum.ROCAUC
    if task.task_type == TaskTypesEnum.regression:
        quality_metric = RegressionMetricsEnum.RMSE
    metrics = [[quality_metric, ComplexityMetricsEnum.computation_time],
               [quality_metric, ComplexityMetricsEnum.structural]]
    multi_obj_sel = [SelectionTypesEnum.spea2]
    selection_types = [multi_obj_sel, multi_obj_sel]
    depth_config_option = [False, False]  # depth configuration option (Active/No active)
    run_multi_obj_exp(history_file=history_file, labels=labels, genetic_schemes_set=genetic_schemes_set, runs=4,
                      metrics=metrics, selection_types=selection_types, depth_config=depth_config_option,
                      train_path=train_path, test_path=test_path, name_of_dataset=name_of_dataset, visualize_hv=True,
                      task=task)


if __name__ == '__main__':
    file_path_train = 'test_cases/scoring/data/scoring_train.csv'
    full_path_train = os.path.join(str(proj_root()), file_path_train)
    file_path_test = 'test_cases/scoring/data/scoring_test.csv'
    full_path_test = os.path.join(str(proj_root()), file_path_test)

    # exp_single_vs_multi_objective()
    exp_self_config_vs_fix_params(train_path=full_path_train, test_path=full_path_test, name_of_dataset='scoring',
                                  task=Task(TaskTypesEnum.classification))
    # exp_multi_obj_selections()
    # exp_complexity_metrics()
