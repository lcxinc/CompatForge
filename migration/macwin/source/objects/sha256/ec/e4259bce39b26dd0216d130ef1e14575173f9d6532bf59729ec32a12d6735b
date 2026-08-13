#define COBJMACROS
#include <windows.h>
#include <oleauto.h>
#include <stdio.h>

static const IID IID_TextMakerDocuments = {
    0xA5F1BE80, 0x163F, 0x11D2,
    {0xA5, 0x82, 0x44, 0x46, 0x49, 0x00, 0x23, 0x5E}
};

static void print_type(const TYPEDESC *type) {
    if (type->vt == VT_PTR && type->lptdesc) {
        wprintf(L"VT_PTR(");
        print_type(type->lptdesc);
        wprintf(L")");
        return;
    }
    if (type->vt == VT_USERDEFINED) {
        wprintf(L"VT_USERDEFINED(0x%lx)", (unsigned long)type->hreftype);
        return;
    }
    wprintf(L"VT_%u", type->vt);
}

int wmain(int argc, wchar_t **argv) {
    ITypeLib *library = NULL;
    ITypeInfo *info = NULL;
    TYPEATTR *attributes = NULL;
    HRESULT status;
    UINT index;
    int found = 0;
    IID interface_id = IID_TextMakerDocuments;
    const wchar_t *member_name = L"Add";

    if (argc != 2 && argc != 4) {
        fwprintf(stderr,
                 L"usage: freeoffice-typeinfo-probe.exe TextMaker.tlb "
                 L"[interface-iid member]\n");
        return 2;
    }
    if (argc == 4) {
        if (FAILED(IIDFromString(argv[2], &interface_id))) {
            fwprintf(stderr, L"invalid interface IID: %ls\n", argv[2]);
            return 2;
        }
        member_name = argv[3];
    }
    status = LoadTypeLibEx(argv[1], REGKIND_NONE, &library);
    if (FAILED(status)) {
        fwprintf(stderr, L"LoadTypeLibEx failed: 0x%08lx\n", status);
        return 3;
    }
    status = ITypeLib_GetTypeInfoOfGuid(library, &interface_id, &info);
    if (FAILED(status)) {
        fwprintf(stderr, L"GetTypeInfoOfGuid failed: 0x%08lx\n", status);
        ITypeLib_Release(library);
        return 4;
    }
    {
        HREFTYPE reference;
        ITypeInfo *vtable_info = NULL;
        status = ITypeInfo_GetRefTypeOfImplType(info, -1, &reference);
        if (SUCCEEDED(status)) status = ITypeInfo_GetRefTypeInfo(info, reference, &vtable_info);
        if (SUCCEEDED(status) && vtable_info) {
            ITypeInfo_Release(info);
            info = vtable_info;
            wprintf(L"VIEW=dual-vtable\n");
        } else {
            wprintf(L"VIEW=dispatch\n");
        }
    }
    status = ITypeInfo_GetTypeAttr(info, &attributes);
    if (FAILED(status)) {
        fwprintf(stderr, L"GetTypeAttr failed: 0x%08lx\n", status);
        ITypeInfo_Release(info);
        ITypeLib_Release(library);
        return 5;
    }

    for (index = 0; index < attributes->cFuncs; ++index) {
        FUNCDESC *function = NULL;
        BSTR names[16] = {0};
        UINT name_count = 0;
        UINT parameter;

        if (FAILED(ITypeInfo_GetFuncDesc(info, index, &function))) continue;
        status = ITypeInfo_GetNames(info, function->memid, names, 16, &name_count);
        if (SUCCEEDED(status) && name_count > 0 &&
            lstrcmpiW(names[0], member_name) == 0) {
            found = 1;
            wprintf(L"NAME=%ls\nMEMID=%ld\nINVKIND=%u\nCALLCONV=%u\n"
                    L"PARAMS=%d\nOPTIONAL=%d\nVFT=%u\nRETURN=",
                    names[0], function->memid, function->invkind, function->callconv,
                    function->cParams, function->cParamsOpt, function->oVft);
            print_type(&function->elemdescFunc.tdesc);
            wprintf(L"\n");
            for (parameter = 0; parameter < (UINT)function->cParams; ++parameter) {
                const ELEMDESC *description = &function->lprgelemdescParam[parameter];
                const wchar_t *name = parameter + 1 < name_count ? names[parameter + 1] : L"";
                wprintf(L"PARAM_%u_NAME=%ls\nPARAM_%u_FLAGS=0x%x\nPARAM_%u_TYPE=",
                        parameter, name, parameter, description->paramdesc.wParamFlags,
                        parameter);
                print_type(&description->tdesc);
                wprintf(L"\n");
                if (description->paramdesc.pparamdescex) {
                    const VARIANT *value = &description->paramdesc.pparamdescex->varDefaultValue;
                    wprintf(L"PARAM_%u_DEFAULT_VT=%u\n", parameter, V_VT(value));
                    if (V_VT(value) == VT_BSTR && V_BSTR(value)) {
                        wprintf(L"PARAM_%u_DEFAULT=%ls\n", parameter, V_BSTR(value));
                    }
                }
            }
        }
        for (parameter = 0; parameter < name_count; ++parameter) SysFreeString(names[parameter]);
        ITypeInfo_ReleaseFuncDesc(info, function);
    }

    ITypeInfo_ReleaseTypeAttr(info, attributes);
    ITypeInfo_Release(info);
    ITypeLib_Release(library);
    return found ? 0 : 6;
}
