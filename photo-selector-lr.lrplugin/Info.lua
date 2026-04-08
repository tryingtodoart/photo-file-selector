return {
    LrSdkVersion        = 6.0,
    LrSdkMinimumVersion = 6.0,

    LrToolkitIdentifier = "com.tryingtodoart.photoselector",
    LrPluginName        = "Photo File Selector",
    LrPluginInfoUrl     = "https://github.com/tryingtodoart/photo-file-selector",

    -- Adds "Photo File Selector…" under Library > Plugin Extras
    LrLibraryMenuItems = {
        {
            title = "Photo File Selector\xe2\x80\xa6",   -- … character
            file  = "PluginMenu.lua",
        },
    },

    VERSION = { major = 1, minor = 0, revision = 0, display = "1.0.0" },
}
