"use strict";

/**
 * 获取url参数（即时函数）
 * 功能：存在debug参数且值为1，则为dev环境。
 */
 (function getUrlParam() {
    let timestampUrl = "";
    let paramStr = window.location.search.substring(1);
    let paramArr = paramStr.split('?');
    let debugParamIndex = paramArr.indexOf('debug=1');
    if (paramArr.length && debugParamIndex > -1) {
        timestampUrl = `${window.location.pathname}?v=${new Date().getTime()}?${paramArr[debugParamIndex]}`;
    } else {
        timestampUrl = `${window.location.pathname}?v=${new Date().getTime()}`;
    }
    window.history.pushState(null, null, timestampUrl);
})();

$(document).keydown(function (event) {
    if (event.keyCode == 13) {
        $("#btnLogin").click();
    }
});

$(function () {
    toastr.options.positionClass = 'toast-top-center';
    $('input').iCheck({
        checkboxClass: 'icheckbox_square-blue',
        radioClass: 'iradio_square-blue',
        increaseArea: '20%' /* optional */
    });
});

angular
    .module("login", [])
    .controller("loginCtrl", ['$scope', '$window', '$http', '$httpParamSerializerJQLike', loginCtrlFn])

function loginCtrlFn($scope, $window, $http, $httpParamSerializerJQLike) {
    /* 依据系统语言获取对应的语言包及当前页面初始化 */
    let loginDynamicTags;
    let g_lang_code;
    let g_ref_lang_dict = {
        "zh": {
            lang_name: "中文（简体）",
            lang_code: "zh"
        },
        "tc": {
            lang_name: "中文（繁體）",
            lang_code: "tc"
        },
        "en": {
            lang_name: "English",
            lang_code: "en"
        },
        "ja": {
            lang_name: "日本語",
            lang_code: "ja"
        },
        "fr": {
            lang_name: "français",  // 法语
            lang_code: "fr"
        },
        "es": {
            lang_name: "Español",   // 西班牙语
            lang_code: "es"
        },
        "ru": {
            lang_name: "Русский",   // 俄语
            lang_code: "ru"
        },
        "ar": {
            lang_name: "العربية",   // 阿拉伯语
            lang_code: "ar"
        },
        "de": {
            lang_name: "Deutsch",   // 德语
            lang_code: "de"
        },
        "pt": {
            lang_name: "Protuguês",     // 葡萄牙语
            lang_code: "pt"
        },
        "hi": {
            lang_name: "हिंदी",    // 印度语
            lang_code: "hi"
        },
        "it": {
            lang_name: "Italiano",  // 意大利语
            lang_code: "it"
        },
        "ko": {
            lang_name: "한국어",    // 韩语
            lang_code: "ko"
        },
        "bn": {
            lang_name: "বাংলা",    // 孟加拉语
            lang_code: "bn"
        },
        "tr": {
            lang_name: "Türkçe",    // 土耳其语
            lang_code: "tr"
        }
    };
    $scope.langDict = {};
    let getRobotActivatedFlg = 0;
    let getLockFlg = 0;
    let getLoginTypeFlg = 0;
    let getLangFlg = 0;
    let storage = $window.sessionStorage;
    if (storage.getItem("loginTipFlag") == 'true') {
        $scope.showPendantTip = true;
        $scope.pendantTip = storage.getItem("loginTip");
    }
    getRollbackStatus();
    getRobotActivatedState();

    /** 登录页面初始化 */
    let initLogin = () => $http.get('./lang/' + g_lang_code + '.json?v=' + new Date().getTime()).success(function (jsonData) {
        loginDynamicTags = jsonData.frontend.login;
        /* 初始化 */
        $scope.collaborativeRobotConsole = jsonData["_collaborative_robot_console"];
        $scope.verifyText = jsonData["_confirm"];
        $scope.cancelText = jsonData["_cancel"];
        $scope.activeText = jsonData["_active"];
        $scope.userNameText = loginDynamicTags.info_messages[0];
        $scope.passwordText = loginDynamicTags.info_messages[1];
        $scope.btnLoginText = loginDynamicTags.info_messages[2];
        $scope.btnUnlockText = loginDynamicTags.info_messages[10];
        $scope.unlockText = loginDynamicTags.info_messages[11];
        $scope.unlockTipsText = loginDynamicTags.info_messages[12];
        $scope.forgetPasswordText = loginDynamicTags.info_messages[3];
        $scope.userIDText = loginDynamicTags.info_messages[5];
        $scope.peopleNameText = loginDynamicTags.info_messages[6];
        $scope.authorityText= loginDynamicTags.info_messages[7];
        $scope.idCardLoginText = loginDynamicTags.info_messages[8];
        $scope.noEnterTipsText = loginDynamicTags.info_messages[9];
        $scope.controlBoxText = loginDynamicTags.info_messages[13];
        /* ./初始化 */
        if (!$window.sessionStorage) {
            alert("The browser does NOT SUPPORT sessionStorage!!!");
        } else {
            storage.setItem("langCode", g_lang_code);
            storage.setItem("langJsonData", JSON.stringify(jsonData));
        }
        // 获取首次激活信息失败提示
        if (!getRobotActivatedFlg) {
            alert(loginDynamicTags.error_messages[10]);
        }
        // 获取WebApp锁定状态失败提示
        if (!getLockFlg) {
            alert(loginDynamicTags.error_messages[7]);
        }
        // 获取登录页面类型失败提示
        if (!getLoginTypeFlg) {
            alert(loginDynamicTags.error_messages[5]);
        }
        // 获取语言标志失败提示
        if (!getLangFlg) {
            alert(loginDynamicTags.error_messages[1]);
        }
    });

    /**
     * 获取是否升级中断出现回滚
     */
    function getRollbackStatus() {
        let cmdContent = {
            cmd: "get_rollback_status"
        };
        $http({
            method: "POST",
            url: "/action/get",
            data: cmdContent
        }).success(function (data) {
            if (data.isRollback) {
                alert(data.tip);
            }
        });
    }

    /* 获取当前语言字典 */
    function getCurrentLangDict() {
        let cmdContent = {
            cmd: "get_lang_dict"
        };
        $http({
            method: "POST",
            url: "/action/get",
            data: cmdContent
        }).success(function (data) {
            for (let i = 0; i < data.length; i++) {
                if (g_ref_lang_dict[data[i]]) {
                    $scope.langDict[data[i]] = g_ref_lang_dict[data[i]];
                } else {
                    $scope.langDict[data[i]] = {
                        lang_name: data[i],
                        lang_code: data[i]
                    };
                }
            }
            getLanguageSetting();
        }).error(function () {
            getLanguageSetting();
        });
    }

    /** 获取系统语言标志 */
    function getLanguageSetting() {
        let cmdContent = {
            cmd: "get_syscfg",
        }
        $http({
            method: "POST",
            url: "/action/get",
            data: cmdContent
        }).success(function (data) {
            g_lang_code = data.language;
            if (Object.keys($scope.langDict).length != 0) {
                $scope.language = $scope.langDict[g_lang_code].lang_name;
            }
            getLangFlg = 1;
            getTeachLocalLanguage();
            initLogin();
        }).error(function () {
            // 如果未获取，默认中文
            g_lang_code = "zh";
            if (Object.keys($scope.langDict).length != 0) {
                $scope.language = $scope.langDict[g_lang_code].lang_name;
            }
            getLangFlg = 0;
            initLogin();
        })
    }

    /** 获取示教器当前语言与WebApp语言匹配状态 */
    function getTeachLocalLanguage() {
        let getCardInfoCmd = {
            cmd: "get_teach_language",
        }
        $http({
            method: "POST",
            url: "/action/get",
            data: getCardInfoCmd
        }).success(function (data) {
            if (!$.isEmptyObject(data)) {
                if (data.isEqual == 0) {
                    $scope.showPendantTip = true;
                    $scope.pendantTip = data.tip;
                }
            }
        })
    }

    /** 获取刷卡信息 */
    function getCardInfo() {
        let getCardInfoCmd = {
            cmd: "get_card_info"
        }
        $http({
            method: "POST",
            url: "/action/get",
            data: getCardInfoCmd
        }).success(function (data) {
            if (!$.isEmptyObject(data)) {
                let dataKeyArr = Object.keys(data);
                if (dataKeyArr.length == 4) {
                    $scope.userID = data.id;
                    $scope.userName = data.name;
                    $scope.password = data.pwd;
                    $scope.authorityName = data.auth;
                    removeClearCardInfoTimeout();
                    createClearCardInfoTimeout();
                } else {
                    alert(`[${data.id}]${$scope.noEnterTipsText}`);
                }
            }
        })
    }
    /** 创建定时器定时获取刷卡信息 */
    let getCardInfoIntervalID;
    function createGetCardInfoInterval() {
        getCardInfoIntervalID = setInterval(() => {
            getCardInfo();
        }, 2000);
    }
    /** 清除定时器 */
    function removeGetCardInfoInterval() {
        if (getCardInfoIntervalID) {
            clearInterval(getCardInfoIntervalID);
        }
    }

    /** 创建定时器定时清除刷卡信息（刷卡后未登录1分钟后清除） */
    let clearCardInfoTimeoutID;
    function createClearCardInfoTimeout() {
        clearCardInfoTimeoutID = setTimeout(() => {
            $scope.userID = "";
            $scope.userName = "";
            $scope.password = "";
            $scope.authorityName = "";
            removeClearCardInfoTimeout();
        }, 5000);
    }
    /** 清除定时器 */
    function removeClearCardInfoTimeout() {
        if (clearCardInfoTimeoutID) {
            clearTimeout(clearCardInfoTimeoutID);
        }
    }

    /** 获取登录页面类型 */
    function getLoginType() {
        let getLoginTypeCmd = {
            cmd: "get_login_type"
        }
        $http({
            method: "POST",
            url: "/action/get",
            data: getLoginTypeCmd
        }).success(function (data) {
            if (getLockFlg && getRobotActivatedFlg) {
                if (data.type == "1") {
                    $scope.if_Login0 = 0;
                    $scope.if_Login1 = 1;
                    // 间隔获取刷卡信息
                    createGetCardInfoInterval();
                } else {
                    $scope.if_Login0 = 1;
                    $scope.if_Login1 = 0;
                }
            } else {
                $scope.if_Login0 = 0;
                $scope.if_Login1 = 0;
            }
            getLoginTypeFlg = 1;
            getCurrentLangDict();
        }).error(function () {
            $scope.if_Login0 = 0;
            $scope.if_Login1 = 0;
            getLoginTypeFlg = 0;
            getCurrentLangDict();
        })
    }

    /* 登录功能 */
    $scope.login = function () {
        let loginData = {
            username: $scope.userName,
            password: $scope.password
        }
        if (loginData.username == null) {
            if ($scope.if_Login1) {
                toastr.warning(loginDynamicTags.info_messages[8]);
            } else if ($scope.if_Login0) {
                toastr.warning(loginDynamicTags.warning_messages[0]);
            }
        } else if (loginData.password == null) {
            if ($scope.if_Login1) {
                toastr.warning(loginDynamicTags.info_messages[8]);
            } else if ($scope.if_Login0) {
                toastr.warning(loginDynamicTags.warning_messages[1]);
            }
        } else {
            $http({
                method: "POST",
                url: "/action/login",
                data: $httpParamSerializerJQLike(loginData),
                headers: { 'Content-type': 'application/x-www-form-urlencoded' },
            }).success(() => {
                storage.setItem("loginTipFlag", false);
                storage.setItem("loginTip", "");
                location = '/index.html';
            }).error((data, status) => {
                if (status == 401) {
                    toastr.error(loginDynamicTags.error_messages[2]);
                } else if (status == 402) {
                    toastr.error(loginDynamicTags.error_messages[3]);
                } else if (status == 403) {
                    toastr.error(loginDynamicTags.error_messages[4]);
                }
            })
        }
    }
    
    /** 进入维护登录页面 */
    $scope.enterMaintenance = function () {
        $scope.isClicked = true;
    }
    
    /**
     * 确认进入维护登录页面密码
     * @param {int} type 确认or取消
     * @param {string} pwd 进入维护登录页面密码
     * @returns 
     */
    $scope.verifyLoginSwitchPwd = function (type, pwd) {
        if (type) {
            if (!pwd) {
                return;
            } else {
                let passwordCmd = {
                    cmd: "verify_login_switch_pwd",
                    data: {
                        pwd: pwd
                    }
                }
                $http({
                    method: "POST",
                    url: "/action/get",
                    data: passwordCmd
                }).success(() => {
                    $scope.if_Login0 = 1;
                    $scope.if_Login1 = 0;
                    $scope.isClicked = false;
                    removeGetCardInfoInterval();
                }).error(() => {
                    toastr.error(loginDynamicTags.error_messages[6]);
                })
            }
        } else {
            $scope.isClicked = false;
            $scope.loginMaintenanceEntrancePwd = null;
        }
    }

    /* 忘记密码 */
    $scope.forgetPassword = function () {
        toastr.info(loginDynamicTags.info_messages[4]);
    }

    /* web界面锁屏信息获取 */
    function getRobotLock() {
        let getRobotLockCmd = {
            cmd: "get_lock_cfg"
        };
        $http({
            method: "POST",
            url: "/action/get",
            data: getRobotLockCmd
        }).success((data) => {
            if (data.day == 0) {
                $scope.isShowLock = true;
            } else {
                $scope.isShowLock = false;
            }
            getLockFlg = 1;
            getLoginType();
        }).error(() => {
            getLockFlg = 0;
            getLoginType();
        });
    }

    /* web界面解锁 */
    $scope.unlock = function () {
        if ($scope.unlockWord == undefined || $scope.unlockWord == null || $scope.unlockWord == '') {
            toastr.warning(loginDynamicTags.warning_messages[2]);
        } else {
            let unlockCmd = {
                cmd: "unlock_webapp",
                data: {
                    key: $scope.unlockWord
                }
            };
            $http({
                method: "POST",
                url: "/action/get",
                data: unlockCmd
            }).success(() => {
                $scope.isShowLock = false;
            }).error(() => {
                toastr.error(loginDynamicTags.error_messages[8]);
            });
        }
    }

    /**
     * web界面控制箱SN码激活
     * @param {string} code 
     */
    $scope.activateRobot = function (code) {
        if (code == undefined || code == null || code == '') {
            toastr.warning(loginDynamicTags.warning_messages[3]);
        } else {
            $scope.activeState = loginDynamicTags.info_messages[15];
            let actCmd = {
                cmd: "set_activation",
                data: {
                    input_SN: code
                }
            };
            $http({
                method: "POST",
                url: "/action/get",
                data: actCmd
            }).success(() => {
                $scope.activeState = '';
                toastr.info(loginDynamicTags.info_messages[14]);
            }).error(() => {
                $scope.activeState = '';
                toastr.error(loginDynamicTags.error_messages[9]);
            });
        }
    }

    /** web界面激活状态信息获取 */
    function getRobotActivatedState() {
        let getCmd = {
            cmd: "get_is_activated"
        };
        $http({
            method: "POST",
            url: "/action/get",
            data: getCmd
        }).success((data) => {
            if (data.isActivated == 0) {
                // 未激活
                $scope.isShowActivateRobot = true;
            } else{
                // 已激活
                $scope.isShowActivateRobot = false;
            }
            getRobotActivatedFlg = 1;
            getRobotLock();
        }).error(() => {
            getRobotActivatedFlg = 0;
            getRobotLock();
        });
    }

    /**
     * 设置系统语言
     * @param {object} selectedLanguage 已选定的语言代码对象
     */
    $scope.setLanguage = function (selectedLanguage) {
        let cmdContent = {
            cmd: "set_sys_language",
            data: {
                language: selectedLanguage.lang_code
            }
        };
        $http({
            method: "POST",
            url: "/action/get",
            data: cmdContent
        }).success((data) => {
            if (!$.isEmptyObject(data)) {
                $scope.showPendantTip = true;
                $scope.pendantTip = data.tip;
                return;
            }
            getRobotActivatedState();
        }).error(() => {
            toastr.error(loginDynamicTags.error_messages[11]);
        });
    }
}

