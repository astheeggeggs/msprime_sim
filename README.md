# msprime sim

*A collection of simulation schemes and methods of anaysis - extensions of LD-score and PCGC.*

The simulation portion of the code allows users to easily generate genotype data under a flexible collection of demographic scenarios and, given this genotype data, generate phenotype information under simple models mapping genotype to phenotype.

Simulation of genetic data wraps the ``msprime`` library which allows extremely efficient sampling from the coalescent with recombination. See the associated [paper](http://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1004842) and [repository](https://github.com/jeromekelleher/msprime).

Note: the code presented here requires the latest and greatest version of ``msprime``: the commit at the time of writing this README was ``dbec779``.

The initial goal of this simulation code was to test extensions of [LD-score](http://www.nature.com/ng/journal/v47/n3/full/ng.3211.html) and [PCGC](http://www.pnas.org/content/111/49/E5272.short). As such, flags can be used to simulate additive, dominance, and gene by environment contributions to phenotype. Further, extensions to the LD-score and PCGC software are implemented here and can be used to attempt to recapitulate these contributions. Details of these extensions can be found below and in the [write-up](https://github.com/astheeggeggs/ldscgxe/tree/master/writeup) of the [``ldscgxe``](https://github.com/astheeggeggs/ldscgxe) repository.

More recently, we have used the wrapper around msprime to simulate demographic scenarios and associated phenotype data to test other methods currently under development in the Neale lab.

We are hopeful that the general simulation schemes provided here may be of use to the human genetics community more broadly.

The code consists of two components, simulation and analysis.

## Simulation
Flags relate to the simulation of genotype information (which calls ``msprime``) and phenotype information, which, conditional on genotype information, determines phenotype data under the specified model.

### General simulation flags
`--out`  
Output filename prefix (Default: `msprimesim`).

`--n-sims`     
Number of msprime simulations to run (Default: 1).

`--fix-genetics`  
Fix the genetic data to be the same across the number of simulations specified by `--n-sims` (Default: False).

`--progress-bars`  
Do you want fancy progress bars? *Warning: Don\'t use this flag when running jobs on a cluster, lest you want tons of printing to your .log file!*

### Genotype
`--write-trees`  
Write the tree sequences generated by `msprime` to PLINK `.bim/.bed/.fam` format?

`--vcf`  
If saving the trees using the `write-trees` flag, do we want to save as `.vcf` file instead?

`--geno-prop`  
What proportion of SNPs are genotyped? (Default: 1).

`--sim-type`  
Type of simulation to run. Currently recognises `standard`, `out-of-africa`, `out-of-africa-all-pops`, and `unicorn` (Default: `standard`).

`--n`  
Number of individuals in the sampled genotypes (Default: 40,000).

`--m`  
Length of the region analysed in nucleotides (Default: 1,000,000).

`--n-chr`  
Number of chromosomes to simulate (Default: 1).

`--Ne`  
Effective population size (Default: 10,000).

`--maf`  
Minor allele frequency cut-off (Default: 0.05).

`--mut`
Mutation rate across the region (Default: 2e-8).

`--rec`  
Recombination rate across the region (Default: 2e-8).

`--rec-map`  
If you want to pass a recombination map, include the filepath here.

`--rec-map-chr`  
If you want to pass a collection of recombination maps, include the filepath here. The filename should contain the symbol @, `msprime_sim` will replace instances of @ with chromosome numbers.

`--no-migration`  
Turn off migration in the demographic history - currently only has an effect for "out-of-africa" and "out-of-africa-all-pops" in the `--sim-type` flag.

`--prop-EUR`  
If using the `unicorn` simulation scenario, what proportion of samples does the European portion make up? (Default: 0.75).
  
### Phenotype
`--write-pheno`
Write the phenotypes to disk

`--h2_A`  
Additive heritability contribution (Default: 0.3).

`--dominance`  
Include dominance contribution to phenotype (Default: False).

`--h2_D`  
Dominance heritability contribution if the `--dominance` flag is used (Default: 0.1).

`--gxe`  
Include a gene by environment contribution to phenotype.

`--h2_AC`  
Gene by environment heritability contribution if the `--gxe` flag is used (Default: 0.2).
  
`--same-causal-sites`  
Causal sites are the same across additive, dominance, and gene x environment contributions (Default: False).
  
`--include-pop-strat`  
Include population stratification in the contribution to the phenotype (Default: False).
  
`--s2`  
Clade associated variance in the phenotype if the `--include-pop-strat` flag is used (Default: 0.1).

`--p-causal`  
'Proportion of SNPs that are causal in the simulations (Default: 1).

`--case-control`  
Run a case-control simulation (Default: False).
  
`--prevalence`  
If using the `case-control` flag, what is the prevalence of the disorder in the population (Default: 0.1)?

`--sample-prevalence`  
If using the `case-control` flag, what is the prevalence of the cases in the study sample (Default: None)? The "None" default keeps the study prevalence the same as the population prevalence.

`--n-cases`
If using the `case-control` flag, what expected number of cases would you like, given the population prevalence provided by `--prevalence` (Default: 1000).

## Analysis
#### LD-score
`--ldsc`  
Perform LD score regression (Default: False).

`--ldscore-sampling-prop`  
Waht proportion of samples are used to determine the LD-scores? If running a large ascertained case-control simulation, you may want to determine LD-score estimates using a subset of the individuals in the full tree to increase speed (Default: None). The default 'None' does not restrict to a subset when determining LD-scores.

`--ld-wind-snps`  
The window size to be used for estimating LD-scores in units of # of SNPs (Default: 1000).

`--no-intercept`  
Constrain the LD-score regression intercept to equal 1 (Default: False).

`--free-and-no-intercept`  
Runs both a free and a constrained intercept equal to 1 (Default: False).

`--linear`  
Force the use of linear regression when using the `--case-control` flag (Default: False)?  

#### PCGC
`--pcgc`  
Estimate heritability using PCGC. *Warning: slow and memory intensive* (Default: False).

  
