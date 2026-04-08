--[[
  Photo File Selector — Lightroom Classic Plugin
  Matches client selections to catalog photos and applies rating / color label.
  https://github.com/tryingtodoart/photo-file-selector
--]]

local LrApplication      = import "LrApplication"
local LrBinding          = import "LrBinding"
local LrColor            = import "LrColor"
local LrDialogs          = import "LrDialogs"
local LrFunctionContext  = import "LrFunctionContext"
local LrPathUtils        = import "LrPathUtils"
local LrPrefs            = import "LrPrefs"
local LrTasks            = import "LrTasks"
local LrView             = import "LrView"

-- WIN_ENV is a global boolean set by Lightroom on Windows (no import needed)
local IS_WIN = WIN_ENV == true

local prefs = LrPrefs.prefsForPlugin()

-- ─────────────────────────────────────────────────────────────────────────────
-- Number extraction  (mirrors the Python logic)
-- ─────────────────────────────────────────────────────────────────────────────

local function escapePattern(s)
    return (s:gsub("([%.%+%-%*%?%[%]%^%$%(%)%%])", "%%%1"))
end

local function zfill(s, width)
    while #s < width do s = "0" .. s end
    return s
end

--- Extract the sequence number from a filename or bare token.
--- "C86A0042-HDR.dng"  prefix="C86A"  digits=4  →  "0042"
--- "155"               prefix="C86A"  digits=4  →  "0155"  (zero-padded)
local function extractNumber(token, prefix, numDigits)
    -- Remove file extension if present
    local stem = token:match("^(.+)%.[^%.]+$") or token
    -- Strip HDR suffix  (case-insensitive: -HDR / _HDR / -hdr …)
    stem = stem:gsub("[%-_][Hh][Dd][Rr]$", "")

    -- Bare number → zero-pad to expected width
    if stem:match("^%d+$") then
        return zfill(stem, numDigits)
    end

    -- Token contains a prefix → extract digits after it
    if prefix ~= "" then
        local pat = "^" .. escapePattern(prefix:upper()) .. "(%d+)"
        local num  = stem:upper():match(pat)
        if num then return num end
    else
        -- Auto-detect: first run of >= numDigits digits
        for run in stem:gmatch("%d+") do
            if #run >= numDigits then
                return run:sub(1, numDigits)
            end
        end
    end

    return nil
end

-- ─────────────────────────────────────────────────────────────────────────────
-- Input parsers
-- ─────────────────────────────────────────────────────────────────────────────

--- Parse arbitrary text (pasted message, file contents).
local function parseText(text, prefix, numDigits)
    local numbers = {}
    for token in text:gmatch("[^%s,;|\t\r\n]+") do
        local num = extractNumber(token, prefix, numDigits)
        if num then numbers[num] = true end
    end
    return numbers
end

--- List filenames in a directory using a shell command.
local function listDir(dirPath)
    local names = {}
    local cmd = IS_WIN
        and ('dir /b "' .. dirPath .. '" 2>nul')
        or  ('ls "' .. dirPath:gsub('"', '\\"') .. '" 2>/dev/null')
    local ok, handle = pcall(io.popen, cmd)
    if ok and handle then
        for line in handle:lines() do
            line = line:match("^%s*(.-)%s*$")
            if line ~= "" then table.insert(names, line) end
        end
        handle:close()
    end
    return names
end

--- Parse a folder of selected images (e.g. client-returned watermarked JPEGs).
local function parseFolder(folderPath, prefix, numDigits)
    local numbers = {}
    for _, name in ipairs(listDir(folderPath)) do
        local num = extractNumber(name, prefix, numDigits)
        if num then numbers[num] = true end
    end
    return numbers
end

--- Parse a plain-text or CSV file.
local function parseTextFile(filePath, prefix, numDigits)
    local numbers = {}
    local f = io.open(filePath, "r")
    if f then
        local content = f:read("*all")
        f:close()
        numbers = parseText(content, prefix, numDigits)
    end
    return numbers
end

--- Merge two sets (tables used as sets).
local function merge(a, b)
    local r = {}
    for k in pairs(a) do r[k] = true end
    for k in pairs(b) do r[k] = true end
    return r
end

--- Count keys in a set.
local function setSize(s)
    local n = 0
    for _ in pairs(s) do n = n + 1 end
    return n
end

-- ─────────────────────────────────────────────────────────────────────────────
-- Catalog search
-- ─────────────────────────────────────────────────────────────────────────────

--- Classify a filename into a type key used by the type filter.
--- Returns one of: "raw", "dng", "hdr", "jpg", "other"
local function getFileTypeKey(filename)
    local stem = filename:match("^(.+)%.[^%.]+$") or filename
    local ext  = (filename:match("%.([^%.]+)$") or ""):lower()
    -- HDR variant (any extension) — check before DNG
    if stem:match("[%-_][Hh][Dd][Rr]$") then return "hdr" end
    if ext == "dng" then return "dng" end
    if ext == "cr2" or ext == "cr3" or ext == "nef" or ext == "arw"
       or ext == "orf" or ext == "rw2" or ext == "raw" or ext == "raf"
       or ext == "3fr" or ext == "mef" or ext == "pef" then return "raw" end
    if ext == "jpg" or ext == "jpeg" then return "jpg" end
    return "other"
end

--- Get photos from the currently active sources (folders / collections)
--- or from the entire catalog.
--- Falls back to getAllPhotos() if active sources return nothing.
local function getPhotos(catalog, currentSourceOnly)
    if not currentSourceOnly then
        return catalog:getAllPhotos()
    end

    local photos  = {}
    local sources = catalog:getActiveSources()
    if sources then
        for _, source in ipairs(sources) do
            -- Check method exists before calling — avoids pcall which blocks
            -- coroutine yields in Lua 5.1 and causes "wait within a task" errors
            if source.getPhotos then
                local sourcePhotos = source:getPhotos()
                if sourcePhotos then
                    for _, p in ipairs(sourcePhotos) do
                        table.insert(photos, p)
                    end
                end
            end
        end
    end

    -- Fallback: active sources yielded nothing — use entire catalog
    if #photos == 0 then
        return catalog:getAllPhotos()
    end

    return photos
end

--- Match photos in the catalog against a set of sequence numbers.
--- typeFilter: table mapping type keys → boolean (nil = use "other" fallback)
--- Returns: matched (array), unmatched (sorted array), totalInScope (number)
local function findMatches(catalog, selectedNumbers, prefix, numDigits, currentSourceOnly, typeFilter)
    local photos     = getPhotos(catalog, currentSourceOnly)
    local matched    = {}
    local numToPhoto = {}   -- number → array of LrPhoto

    for _, photo in ipairs(photos) do
        -- Prefer getFormattedMetadata; fall back to path leaf name
        local filename = photo:getFormattedMetadata("fileName")
        if not filename or filename == "" then
            local path = photo:getRawMetadata("path")
            if path then filename = LrPathUtils.leafName(path) end
        end

        if filename and filename ~= "" then
            -- Apply file-type filter
            local typeKey = getFileTypeKey(filename)
            local include = typeFilter[typeKey]
            if include == nil then include = typeFilter["other"] end
            if include == nil then include = true end  -- default: include

            if include then
                local num = extractNumber(filename, prefix, numDigits)
                if num then
                    if not numToPhoto[num] then numToPhoto[num] = {} end
                    table.insert(numToPhoto[num], photo)
                end
            end
        end
    end

    local unmatched = {}
    for num in pairs(selectedNumbers) do
        if numToPhoto[num] then
            for _, p in ipairs(numToPhoto[num]) do
                table.insert(matched, p)
            end
        else
            table.insert(unmatched, num)
        end
    end

    table.sort(unmatched)
    return matched, unmatched, #photos
end

-- ─────────────────────────────────────────────────────────────────────────────
-- Main dialog
-- ─────────────────────────────────────────────────────────────────────────────

LrTasks.startAsyncTask(function()
LrFunctionContext.callWithContext("Photo File Selector", function(context)

    local catalog = LrApplication.activeCatalog()
    local f       = LrView.osFactory()

    -- Property table — all UI values live here
    local props = LrBinding.makePropertyTable(context)
    props.selPath          = ""
    props.pasteText        = ""
    props.prefix           = prefs.prefix     or ""
    props.numDigits        = prefs.numDigits  or 4
    props.scopeCurrent     = (prefs.scopeCurrent ~= false)  -- default: current source
    props.applyRating      = prefs.applyRating  or false
    props.ratingValue      = prefs.ratingValue  or 3
    props.applyLabel       = (prefs.applyLabel ~= false)    -- default: on
    props.labelValue       = prefs.labelValue   or "red"
    -- File-type filters
    props.inclRAW          = (prefs.inclRAW  ~= false)   -- CR2, NEF, ARW, …
    props.inclDNG          = (prefs.inclDNG  ~= false)
    props.inclHDR          = (prefs.inclHDR  ~= false)
    props.inclJPG          = (prefs.inclJPG  ~= false)
    props.inclOther        = (prefs.inclOther ~= false)
    props.statusText       = "Set up your selection, then click Preview."
    props.statusColor      = LrColor(0.45, 0.45, 0.45)
    props.previewDone      = false

    -- These are populated by runPreview and read by Apply
    local matchedPhotos    = {}
    local unmatchedNumbers = {}

    -- ── Preview ──────────────────────────────────────────────────────────────
    local function runPreview()
        local selPath  = props.selPath
        local paste    = props.pasteText or ""
        local prefix   = props.prefix:upper()
        local digits   = tonumber(props.numDigits) or 4

        if selPath == "" and paste:match("^%s*$") then
            props.statusText  = "Please provide a selection (path or pasted text)."
            props.statusColor = LrColor(0.7, 0.2, 0.2)
            return
        end

        props.statusText  = "Parsing selection\xe2\x80\xa6"
        props.statusColor = LrColor(0.45, 0.45, 0.45)
        props.previewDone = false

        -- Collect numbers from all provided inputs
        local numbers = {}

        if selPath ~= "" then
            local ext = LrPathUtils.extension(selPath):lower()
            if ext == "txt" or ext == "csv" then
                numbers = merge(numbers, parseTextFile(selPath, prefix, digits))
            else
                -- No extension or image extension → treat as folder
                numbers = merge(numbers, parseFolder(selPath, prefix, digits))
            end
        end

        if not paste:match("^%s*$") then
            numbers = merge(numbers, parseText(paste, prefix, digits))
        end

        local numCount = setSize(numbers)
        if numCount == 0 then
            props.statusText  = "No numbers found. Check prefix / digit settings."
            props.statusColor = LrColor(0.7, 0.2, 0.2)
            return
        end

        local scope = props.scopeCurrent and "selected source" or "entire catalog"
        props.statusText = "Found " .. numCount .. " number(s). Searching " .. scope .. "\xe2\x80\xa6"

        -- Build type filter from checkboxes
        local typeFilter = {
            raw   = props.inclRAW,
            dng   = props.inclDNG,
            hdr   = props.inclHDR,
            jpg   = props.inclJPG,
            other = props.inclOther,
        }

        local photoCount
        matchedPhotos, unmatchedNumbers, photoCount = findMatches(
            catalog, numbers, prefix, digits, props.scopeCurrent, typeFilter)

        -- Save prefs
        prefs.prefix        = props.prefix
        prefs.numDigits     = props.numDigits
        prefs.scopeCurrent  = props.scopeCurrent
        prefs.applyRating   = props.applyRating
        prefs.ratingValue   = props.ratingValue
        prefs.applyLabel    = props.applyLabel
        prefs.labelValue    = props.labelValue
        prefs.inclRAW       = props.inclRAW
        prefs.inclDNG       = props.inclDNG
        prefs.inclHDR       = props.inclHDR
        prefs.inclJPG       = props.inclJPG
        prefs.inclOther     = props.inclOther

        props.previewDone = true

        local msg = #matchedPhotos .. " photo(s) matched"
            .. " (searched " .. photoCount .. " in " .. scope .. ")"
        if #unmatchedNumbers > 0 then
            msg = msg .. " \xe2\x80\x94 " .. #unmatchedNumbers .. " number(s) not found"
        end
        props.statusText  = msg
        props.statusColor = #matchedPhotos > 0
            and LrColor(0.05, 0.45, 0.05)
            or  LrColor(0.7, 0.2, 0.2)
    end

    -- ── Rating / label menu items ─────────────────────────────────────────────
    local ratingItems = {
        { title = "1 star",     value = 1 },
        { title = "2 stars",    value = 2 },
        { title = "3 stars",    value = 3 },
        { title = "4 stars",    value = 4 },
        { title = "5 stars",    value = 5 },
        { title = "No rating",  value = 0 },
    }
    local labelItems = {
        { title = "Red",    value = "red"    },
        { title = "Yellow", value = "yellow" },
        { title = "Green",  value = "green"  },
        { title = "Blue",   value = "blue"   },
        { title = "Purple", value = "purple" },
        { title = "None",   value = ""       },
    }

    -- ── Dialog UI ─────────────────────────────────────────────────────────────
    local contents = f:column {
        bind_to_object = props,
        spacing        = f:control_spacing(),
        fill_horizontal = 1,

        -- ── Client Selection ──────────────────────────────────────────────────
        f:group_box {
            title           = "Client Selection",
            fill_horizontal = 1,

            f:row {
                spacing = f:label_spacing(),
                f:push_button {
                    title  = "Folder selection",
                    action = function()
                        local path = LrDialogs.runOpenPanel {
                            title                   = "Select Folder of Client-Selected Images",
                            canChooseFiles          = false,
                            canChooseDirectories    = true,
                            allowsMultipleSelection = false,
                        }
                        if path and path[1] then props.selPath = path[1] end
                    end,
                },
                f:static_text {
                    title      = "A folder of the client\xe2\x80\x99s chosen images (JPG, JPEG, \xe2\x80\xa6)",
                    text_color = LrColor(0.45, 0.45, 0.45),
                },
            },
            f:row {
                spacing = f:label_spacing(),
                f:push_button {
                    title  = "File selection",
                    action = function()
                        local path = LrDialogs.runOpenPanel {
                            title                   = "Select Number List File",
                            canChooseFiles          = true,
                            canChooseDirectories    = false,
                            allowsMultipleSelection = false,
                        }
                        if path and path[1] then props.selPath = path[1] end
                    end,
                },
                f:static_text {
                    title      = "A .txt or .csv file with image numbers",
                    text_color = LrColor(0.45, 0.45, 0.45),
                },
            },
            f:edit_field {
                value              = LrView.bind "selPath",
                fill_horizontal    = 1,
                placeholder_string = "Selected path appears here \xe2\x80\x94 or type / paste a path directly",
            },

            f:static_text {
                title      = "Or paste a message / number list:",
                text_color = LrColor(0.45, 0.45, 0.45),
            },
            f:row {
                f:edit_field {
                    value              = LrView.bind "pasteText",
                    fill_horizontal    = 1,
                    height_in_lines    = 3,
                    placeholder_string = 'e.g.  "Please send 155, 175 and 320"  or just  155, 175, 320',
                },
                f:push_button {
                    title  = "Clear",
                    action = function() props.pasteText = "" end,
                },
            },
        },

        -- ── Filename Settings ─────────────────────────────────────────────────
        f:group_box {
            title           = "Filename Settings",
            fill_horizontal = 1,

            f:row {
                spacing = f:label_spacing(),
                f:static_text { title = "Prefix:" },
                f:edit_field {
                    value              = LrView.bind "prefix",
                    width_in_chars     = 10,
                    placeholder_string = "e.g. C86A",
                },
                f:spacer { width = 20 },
                f:static_text { title = "Sequence digits:" },
                f:edit_field {
                    value          = LrView.bind "numDigits",
                    width_in_chars = 4,
                },
            },
        },

        -- ── Search Scope ──────────────────────────────────────────────────────
        f:group_box {
            title           = "Search Scope",
            fill_horizontal = 1,

            f:radio_button {
                title         = "Currently selected folder / collection",
                value         = LrView.bind "scopeCurrent",
                checked_value = true,
            },
            f:radio_button {
                title         = "Entire catalog",
                value         = LrView.bind "scopeCurrent",
                checked_value = false,
            },
        },

        -- ── File Types ────────────────────────────────────────────────────────
        f:group_box {
            title           = "File types to include",
            fill_horizontal = 1,

            f:row {
                spacing = f:label_spacing(),
                f:checkbox { title = "RAW (CR2/NEF/ARW\xe2\x80\xa6)", value = LrView.bind "inclRAW"   },
                f:checkbox { title = "DNG",                            value = LrView.bind "inclDNG"   },
                f:checkbox { title = "DNG (HDR)",                      value = LrView.bind "inclHDR"   },
                f:checkbox { title = "JPG",                            value = LrView.bind "inclJPG"   },
                f:checkbox { title = "Other",                          value = LrView.bind "inclOther" },
            },
        },

        -- ── Action ────────────────────────────────────────────────────────────
        f:group_box {
            title           = "Action to apply to matched photos",
            fill_horizontal = 1,

            f:row {
                spacing = f:label_spacing(),
                f:checkbox  { title = "Set star rating:", value = LrView.bind "applyRating" },
                f:popup_menu {
                    value   = LrView.bind "ratingValue",
                    items   = ratingItems,
                    enabled = LrView.bind "applyRating",
                },
            },
            f:row {
                spacing = f:label_spacing(),
                f:checkbox  { title = "Set color label:", value = LrView.bind "applyLabel" },
                f:popup_menu {
                    value   = LrView.bind "labelValue",
                    items   = labelItems,
                    enabled = LrView.bind "applyLabel",
                },
            },
        },

        -- ── Preview row ───────────────────────────────────────────────────────
        f:row {
            spacing = f:label_spacing(),
            f:push_button {
                title  = "Preview",
                action = function()
                    LrTasks.startAsyncTask(runPreview)
                end,
            },
            f:static_text {
                value      = LrView.bind "statusText",
                text_color = LrView.bind "statusColor",
                fill_horizontal = 1,
            },
        },
    }

    -- ── Present dialog ────────────────────────────────────────────────────────
    local result = LrDialogs.presentModalDialog {
        title      = "Photo File Selector",
        contents   = contents,
        actionVerb = "Apply",
        cancelVerb = "Cancel",
    }

    -- ── Apply ─────────────────────────────────────────────────────────────────
    if result == "ok" then

        if not props.previewDone then
            -- User hit Apply without running Preview — run both now
            runPreview()
        end

        if #matchedPhotos == 0 then
            LrDialogs.message(
                "Nothing to apply",
                "No matching photos were found. Check your selection and scope settings.",
                "info")
            return
        end

        if not props.applyRating and not props.applyLabel then
            LrDialogs.message(
                "No action selected",
                "Please tick at least one action (star rating or color label).",
                "info")
            return
        end

        local ratingVal = tonumber(props.ratingValue) or 0
        local labelVal  = props.labelValue

        catalog:withWriteAccessDo("Photo File Selector", function()
            for _, photo in ipairs(matchedPhotos) do
                if props.applyRating then
                    photo:setRawMetadata("rating", ratingVal)
                end
                if props.applyLabel then
                    photo:setRawMetadata("colorNameForLabel", labelVal)
                end
            end
        end)

        -- Final summary
        local msg = "Applied to " .. #matchedPhotos .. " photo(s)."
        if #unmatchedNumbers > 0 then
            msg = msg .. "\n\nNumbers not found in scope ("
                .. #unmatchedNumbers .. "):\n"
                .. table.concat(unmatchedNumbers, ",  ")
        end
        LrDialogs.message("Done", msg, "info")
    end

end) -- end callWithContext
end) -- end startAsyncTask
