#!/usr/bin/env groovy

String tarquinBranch = "TNC/tnc-o-tracking#3408"

library "tarquin@$tarquinBranch"

pipelinePy {
  pkgInfoPath = 'osvimdriver/pkg_info.json'
  applicationName = 'os-vim-driver'
  releaseArtifactsPath = 'release-artifacts'
  attachDocsToRelease = true
  attachHelmToRelease = true
}
