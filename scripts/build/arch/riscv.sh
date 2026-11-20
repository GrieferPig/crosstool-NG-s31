# Compute RISC-V-specific values

CT_DoArchTupleValues() {
    CT_TARGET_ARCH="riscv${CT_ARCH_BITNESS}"
}

# uClibc-ng has separate syscall/CRT implementations for the two XLENs.
CT_DoArchUClibcConfig() {
    CT_DoArchUClibcSelectArch "${1}" "riscv${CT_ARCH_BITNESS}"
    if [ "${CT_ARCH_ABI}" = ilp32 ] || [ "${CT_ARCH_ABI}" = lp64 ]; then
        CT_KconfigDisableOption "UCLIBC_HAS_FPU" "${1}"
        CT_KconfigEnableOption "UCLIBC_HAS_FLOATS" "${1}"
    fi
}
