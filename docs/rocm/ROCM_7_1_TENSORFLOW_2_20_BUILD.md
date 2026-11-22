# TensorFlow 2.20.0 with ROCm 7.1 and Clang 21: build record

**Status:** GPU kernel compilation and linking validated; Python wheel and runtime GPU execution **not yet validated**.
**Recorded:** 2026-11-22
**Repository:** `battleblazer101/tensorflow`
**Branch:** `rocm-7.1-compat`
**Target host:** `ai-server` (Kubuntu 26.04.1)

## 1. Purpose and scope

This record describes the compatibility changes and successful build of TensorFlow 2.20.0 GPU targets with ROCm 7.1 and LLVM/Clang 21. It distinguishes confirmed results from work still outstanding. Radeon 680M hardware reports `gfx1035`; the build uses `gfx1030` as a compatibility target. Successful compilation is **not** evidence of runtime correctness on `gfx1035`.

## 2. Environment and preservation constraints

| Component | Recorded value |
| --- | --- |
| OS | Kubuntu 26.04.1 |
| TensorFlow | 2.20.0 custom compatibility branch |
| ROCm | 7.1.0 |
| HIP | 7.1.1 |
| LLVM/Clang | 21, via `/usr/lib/llvm-21/bin` |
| Bazel | 7.4.1, `~/venvs/py312_ml/bin/bazel` |
| Python | Hermetic 3.12 |
| GPU | Radeon 680M, build target `gfx1030` |
| ROCm compatibility tree | `~/ai-stuff/rocm-compat` |
| TensorFlow worktree | `~/ai-stuff/tensorflow-rocm71-worktree` |
| Private resource overlay | `~/ai-stuff/rocm-compat/clang21-resource-overlay` |

Production change control: **do not run `bazel clean`, delete Bazel caches, modify system LLVM headers, or disrupt LibreChat, PostgreSQL, ComfyUI, or JupyterLab.** Use `uv` and `~/venvs` for new test environments.

## 3. Failure history and fixes

### 3.1 AMDGPU device-linking failures

An earlier targeted build failed with unresolved symbols in Clang HIP complex builtins:

```text
lld: error: undefined symbol: isnan(float)
>>> referenced by (__mulsc3)
lld: error: undefined symbol: isinf(float)
>>> referenced by (__mulsc3)
lld: error: undefined symbol: isnan(double)
>>> referenced by (__muldc3)
lld: error: undefined symbol: isinf(double)
>>> referenced by (__muldc3)
clang++: error: amdgcn-link command failed
```

Instead of changing system LLVM, we generated a **private Clang 21 resource overlay** with links to the installed resource headers and a patched `__clang_cuda_complex_builtins.h`. The generator made six substitutions (four concerning `isnan`/`isinf`, two changing `max` to `fmax` for device math). A direct HIP float-complex compile/link smoke test succeeded.

Generator: `tools/rocm/create_clang21_resource_overlay.py`. Relevant commits: `55790db890fc7b057b0fe7adca74f92f27ebb9a8`, corrected by `731f72b205802b1f64535fa47e35cedeed19712c`. The committed generator is authoritative for exact transformations.

### 3.2 Bazel rejected absolute-path headers

Passing `-resource-dir` to HIPCC exposed a separate toolchain configuration issue: hundreds of GPU compilation actions reported undeclared absolute-path includes such as:

```text
absolute path inclusion(s) found in rule '@@local_xla//xla/stream_executor/rocm:all_reduce_kernel_rocm'
'/home/user/ai-stuff/rocm-compat/clang21-resource-overlay/include/stddef.h'
'/home/user/ai-stuff/rocm-compat/clang21-resource-overlay/include/__clang_cuda_complex_builtins.h'
```

The unsuccessful large build ran for approximately 3,334 seconds. The overlay files were not yet registered as compiler built-in include directories.

### 3.3 Bazel toolchain registration

Commit `c7f4e138c89d88a925e21a946f1cea853ec9b6e9` modified `third_party/xla/third_party/gpus/rocm_configure.bzl`, adding the repository environment variable `TF_ROCM_CLANG_RESOURCE_DIR` to `_ENVIRONS` and the following logic to `_rocm_include_path`:

```python
overlay_dir = get_host_environ(repository_ctx, "TF_ROCM_CLANG_RESOURCE_DIR")
if overlay_dir:
    inc_dirs.append(overlay_dir.rstrip("/") + "/include")
```

After `bazel sync --only=local_config_rocm` with matching `--repo_env` arguments, the generated `external/local_config_rocm/crosstool/BUILD` contained `/home/user/ai-stuff/rocm-compat/clang21-resource-overlay/include` in `cxx_builtin_include_directories`. The generated `cc_toolchain_config.bzl` merely defines the rule; the configured values are in `crosstool/BUILD`. Keep `--repo_env=TF_ROCM_CLANG_RESOURCE_DIR=...` on **every subsequent build** or Bazel may regenerate a configuration without the overlay.

### 3.4 Eigen compatibility

An additional compatibility patch lives at `third_party/xla/third_party/eigen3/rocm_clang21_device_math.patch` (commit `f23c51d3e724215620be4356929a3109d7aac125`). After fixing patch formatting, `bazel sync --only=eigen_archive` succeeded. See the committed patch for exact changes.

## 4. Working build configuration

```bash
PATH="/usr/lib/llvm-21/bin:$PATH"
ROCM_PATH="$HOME/ai-stuff/rocm-compat"
TF_NEED_ROCM=1
TF_ROCM_AMDGPU_TARGETS=gfx1030
TF_ROCM_CLANG_RESOURCE_DIR="$HOME/ai-stuff/rocm-compat/clang21-resource-overlay"
HIPCC_COMPILE_FLAGS_APPEND="-isystem /usr/lib/llvm-21/lib/clang/21 -resource-dir=$HOME/ai-stuff/rocm-compat/clang21-resource-overlay"
```

Pass the relevant values both as process environment variables and as Bazel `--repo_env` values. The tested large-build command below prints output to the terminal and writes a log:

```bash
set -o pipefail && cd ~/ai-stuff/tensorflow-rocm71-worktree && PATH="/usr/lib/llvm-21/bin:$PATH" ROCM_PATH="$HOME/ai-stuff/rocm-compat" TF_NEED_ROCM=1 TF_ROCM_AMDGPU_TARGETS=gfx1030 TF_ROCM_CLANG_RESOURCE_DIR="$HOME/ai-stuff/rocm-compat/clang21-resource-overlay" HIPCC_COMPILE_FLAGS_APPEND="-isystem /usr/lib/llvm-21/lib/clang/21 -resource-dir=$HOME/ai-stuff/rocm-compat/clang21-resource-overlay" ~/venvs/py312_ml/bin/bazel build --config=rocm --keep_going --jobs=6 --copt=-Wno-error=discarded-qualifiers --action_env=PATH="/usr/lib/llvm-21/bin:$PATH" --repo_env=TF_NEED_ROCM=1 --repo_env=HERMETIC_PYTHON_VERSION=3.12 --repo_env=ROCM_PATH="$HOME/ai-stuff/rocm-compat" --repo_env=TF_ROCM_AMDGPU_TARGETS=gfx1030 --repo_env=TF_ROCM_CLANG_RESOURCE_DIR="$HOME/ai-stuff/rocm-compat/clang21-resource-overlay" --repo_env=HIPCC_COMPILE_FLAGS_APPEND="-isystem /usr/lib/llvm-21/lib/clang/21 -resource-dir=$HOME/ai-stuff/rocm-compat/clang21-resource-overlay" //tensorflow/core/kernels:cwise_op_gpu 2>&1 | tee ~/ai-stuff/tensorflow-rocm71-build-retry.log
```

`--jobs=6` means concurrent Bazel actions, not OS threads. `set -o pipefail` preserves Bazel's failure status through `tee`. `--keep_going` allows independent actions to continue; always inspect the final status. **Do not clear the cache.**

## 5. Confirmed build results — 2026-11-22

### 5.1 Focused ROCm target

The previously failing target was built with the same environment, `--jobs=2`, and log `~/ai-stuff/tensorflow-rocm71-focused-test.log`. The correct external-repository label has an `@` prefix: `@local_xla//xla/stream_executor/rocm:all_reduce_kernel_rocm`. The earlier incorrect label `//local_xla/...` failed during target parsing without compiling anything.

```text
Target @@local_xla//xla/stream_executor/rocm:all_reduce_kernel_rocm up-to-date:
  bazel-bin/external/local_xla/xla/stream_executor/rocm/liball_reduce_kernel_rocm.lo
  bazel-bin/external/local_xla/xla/stream_executor/rocm/liball_reduce_kernel_rocm.pic.lo
  bazel-bin/external/local_xla/xla/stream_executor/rocm/liball_reduce_kernel_rocm.so
INFO: Elapsed time: 532.860s, Critical Path: 37.28s
INFO: 714 processes: 2 internal, 712 local.
INFO: Build completed successfully, 714 total actions
```

### 5.2 TensorFlow GPU kernel target

```text
Target //tensorflow/core/kernels:cwise_op_gpu up-to-date:
  bazel-bin/tensorflow/core/kernels/libcwise_op_gpu.lo
  bazel-bin/tensorflow/core/kernels/libcwise_op_gpu.pic.lo
  bazel-bin/tensorflow/core/kernels/libcwise_op_gpu.so
INFO: Elapsed time: 3128.754s, Critical Path: 131.20s
INFO: 4958 processes: 1 internal, 4957 local.
INFO: Build completed successfully, 4958 total actions
```

The large target built successfully in **52 minutes 9 seconds**, with **4,958 actions**. These results show that the prior header dependency and device-link errors no longer block the tested targets. They do **not** prove that every TensorFlow target builds, that a Python wheel imports, or that GPU execution works on the Radeon 680M.

## 6. Remaining validation

1. Record the exact Git commit and tag for this **GPU kernel build milestone**, without claiming wheel/runtime validation.
2. Confirm the local overlay can be regenerated from the committed script.
3. Build a TensorFlow Python wheel with the same toolchain and ROCm configuration.
4. Create a dedicated test environment under `~/venvs` using `uv`, without replacing the current ML environment.
5. Test TensorFlow import, GPU enumeration, elementwise operations, matrix multiplication, CPU/GPU numerical agreement, and repeated execution.
6. Stress-test stability and GPU memory on the Radeon 680M, accounting for 8 GB configured shared VRAM and `gfx1030`-on-`gfx1035` compatibility.
7. Retain terminal logs and clearly distinguish build success from runtime validation.

## 7. Reproducibility caveats

- The Clang resource overlay is generated locally; its **generator** is version-controlled, but the generated overlay is not asserted to be committed.
- The full contents, provenance, and hashes of the local `ROCM_PATH` compatibility tree are not inventoried here.
- A local `~/ai-stuff/rocm-compat/tf_hip_clang21_compat.h` exists but is not asserted to be in Git; inventory its role before claiming complete reproducibility.
- The exact upstream TensorFlow base and complete branch diff have not been independently audited in this document.
- System LLVM and production packages should not be modified to reproduce this milestone.

## 8. Milestone tag

Tag the documentation commit on `rocm-7.1-compat` with a name that reflects **successful GPU kernel compilation and linking only**. Suggested annotated tag: `tf2.20-rocm7.1-gpu-kernels-build-ok`, message: `TensorFlow 2.20 ROCm 7.1 GPU kernel build succeeds; wheel and runtime unverified`. Verify the branch head and local worktree state before tagging; do not tag a dirty or unexpected revision.
