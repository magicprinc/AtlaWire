<!-- Bitbucket Server 5.10.0 REST API — section: 02-index -->

## Index

Provides REST resources

- [Resources](#resources)
  -

     

  - [http://example.com/rest/api/1.0/admin](#idm532026142528)
    -

    - [http://example.com/rest/api/1.0/admin/groups](#idm532026140912) \[[GET](#idm532026140272), [POST](#idm532026132944), [DELETE](#idm532026122064)\]

    - [http://example.com/rest/api/1.0/admin/groups/add-user](#idm532064578848) \[[POST](#idm532064576992)\]

    - [http://example.com/rest/api/1.0/admin/groups/add-users](#idm532027401936) \[[POST](#idm532027401440)\]

    - [http://example.com/rest/api/1.0/admin/groups/more-members](#idm532027388832) \[[GET](#idm532027388464)\]

    - [http://example.com/rest/api/1.0/admin/groups/more-non-members](#idm532027380496) \[[GET](#idm532027378592)\]

    - [http://example.com/rest/api/1.0/admin/groups/remove-user](#idm532061981920) \[[POST](#idm532061972672)\]

    - [http://example.com/rest/api/1.0/admin/users](#idm532026105008) \[[GET](#idm532026104352), [PUT](#idm532026097696), [POST](#idm532026084976), [DELETE](#idm532026064704)\]

    - [http://example.com/rest/api/1.0/admin/users/add-group](#idm532063441504) \[[POST](#idm532063441248)\]

    - [http://example.com/rest/api/1.0/admin/users/add-groups](#idm532061983296) \[[POST](#idm532061983008)\]

    - [http://example.com/rest/api/1.0/admin/users/captcha](#idm532064589152) \[[DELETE](#idm532064588656)\]

    - [http://example.com/rest/api/1.0/admin/users/credentials](#idm532025490784) \[[PUT](#idm532025489664)\]

    - [http://example.com/rest/api/1.0/admin/users/more-members](#idm532027370176) \[[GET](#idm532027369184)\]

    - [http://example.com/rest/api/1.0/admin/users/more-non-members](#idm532027361472) \[[GET](#idm532027360800)\]

    - [http://example.com/rest/api/1.0/admin/users/remove-group](#idm532063436400) \[[POST](#idm532063436144)\]

    - [http://example.com/rest/api/1.0/admin/users/rename](#idm532027412768) \[[POST](#idm532027413936)\]

     

  - [http://example.com/rest/api/1.0/admin/cluster](#idm532026187008) \[[GET](#idm532026185216)\]

     

  - [http://example.com/rest/api/1.0/admin/license](#idm532025970944) \[[GET](#idm532025970192), [POST](#idm532025961888)\]

     

  - [http://example.com/rest/api/1.0/admin/mail-server](#idm532023689168) \[[DELETE](#idm532023687232), [GET](#idm532023683088), [PUT](#idm532023675872)\]
    -

    - [http://example.com/rest/api/1.0/admin/mail-server/sender-address](#idm532023665808) \[[DELETE](#idm532023665552), [GET](#idm532023661088), [PUT](#idm532023654720)\]

     

  - [http://example.com/rest/api/1.0/admin/permissions](#idm532026348384)
    -

    - [http://example.com/rest/api/1.0/admin/permissions/groups](#idm532026311408) \[[PUT](#idm532026310912), [GET](#idm532026294496), [DELETE](#idm532026287728)\]

    - [http://example.com/rest/api/1.0/admin/permissions/groups/none](#idm532026269120) \[[GET](#idm532026267168)\]

    - [http://example.com/rest/api/1.0/admin/permissions/users](#idm532026347376) \[[PUT](#idm532026346992), [GET](#idm532026330240), [DELETE](#idm532026323344)\]

    - [http://example.com/rest/api/1.0/admin/permissions/users/none](#idm532026275728) \[[GET](#idm532026275232)\]

     

  - [http://example.com/rest/api/1.0/admin/pull-requests/{scmId}](#idm532025993376) \[[POST](#idm532025991824), [GET](#idm532025979888)\]

     

  - [http://example.com/rest/api/1.0/application-properties](#idm532026378624) \[[GET](#idm532026377424)\]

     

  - [http://example.com/rest/api/1.0/dashboard](#idm532061756624)
    -

    - [http://example.com/rest/api/1.0/dashboard/pull-request-suggestions](#idm532061755120) \[[GET](#idm532061754864)\]

    - [http://example.com/rest/api/1.0/dashboard/pull-requests](#idm532061745200) \[[GET](#idm532061743296)\]

     

  - [http://example.com/rest/api/1.0/groups](#idm532025402208) \[[GET](#idm532025403200)\]

     

  - [http://example.com/rest/api/1.0/hooks](#idm532025356240)
    -

    - [http://example.com/rest/api/1.0/hooks/{hookKey}/avatar](#idm532025356112) \[[GET](#idm532025353744)\]

     

  - [http://example.com/rest/api/1.0/inbox](#idm532026148208)
    -

    - [http://example.com/rest/api/1.0/inbox/pull-requests](#idm532026146592) \[[GET](#idm532026146912)\]

    - [http://example.com/rest/api/1.0/inbox/pull-requests/count](#idm532026149280) \[[GET](#idm532026147840)\]

     

  - [http://example.com/rest/api/1.0/logs](#idm532027255840)
    -

    - [http://example.com/rest/api/1.0/logs/logger/{loggerName}](#idm532027256864) \[[GET](#idm532027254144)\]

    - [http://example.com/rest/api/1.0/logs/logger/{loggerName}/{levelName}](#idm532025472384) \[[PUT](#idm532063422448)\]

    - [http://example.com/rest/api/1.0/logs/rootLogger](#idm532063415184) \[[GET](#idm532063415056)\]

    - [http://example.com/rest/api/1.0/logs/rootLogger/{levelName}](#idm532063408880) \[[PUT](#idm532027247872)\]

     

  - [http://example.com/rest/api/1.0/markup](#idm532063356496)
    -

    - [http://example.com/rest/api/1.0/markup/preview](#idm532063357696) \[[POST](#idm532063356096)\]

     

  - [http://example.com/rest/api/1.0/profile/recent/repos](#idm532023761296) \[[GET](#idm532023760096)\]

     

  - [http://example.com/rest/api/1.0/projects](#idm532026446992) \[[GET](#idm532026448016), [POST](#idm532026440192)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}](#idm532026426032) \[[GET](#idm532026426656), [DELETE](#idm532026418784), [PUT](#idm532026408272)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/avatar.png](#idm532026393088) \[[GET](#idm532026392592), [POST](#idm532026384208)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions](#idm532027240944)
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/groups](#idm532027222704) \[[PUT](#idm532063398752), [GET](#idm532025460784), [DELETE](#idm532025454368)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/groups/none](#idm532027217712) \[[GET](#idm532027217120)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/users](#idm532027240592) \[[PUT](#idm532027240336), [GET](#idm532063408256), [DELETE](#idm532063401824)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/users/none](#idm532025453984) \[[GET](#idm532025453408)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/{permission}/all](#idm532027230128) \[[POST](#idm532025470032), [GET](#idm532025463088)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos](#idm532026524400) \[[POST](#idm532026523120), [GET](#idm532026511200)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}](#idm532025663472) \[[GET](#idm532025661856), [PUT](#idm532025659792), [DELETE](#idm532025636784), [POST](#idm532025629360)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/forks](#idm532025616608) \[[GET](#idm532025615120)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/recreate](#idm532025599632) \[[POST](#idm532025599376)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/related](#idm532025606624) \[[GET](#idm532025607664)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/archive](#idm532025516960) \[[GET](#idm532025515040)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches](#idm532065002640) \[[POST](#idm532065001520), [GET](#idm532061935136)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches/default](#idm532023779664) \[[GET](#idm532023778192), [PUT](#idm532023769856)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse](#idm532027352368) \[[GET](#idm532027351696)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse/{path:.\*}](#idm532027334656) \[[GET](#idm532027333712), [PUT](#idm532027316624)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/changes](#idm532025564880) \[[GET](#idm532025563888)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits](#idm532027292144) \[[GET](#idm532027291648)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}](#idm532027270128) \[[GET](#idm532027268832)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/changes](#idm532061686512) \[[GET](#idm532061685168)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments](#idm532025948608) \[[GET](#idm532025946144), [POST](#idm532025933648)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}](#idm532023804640) \[[GET](#idm532023802176), [DELETE](#idm532023793904), [PUT](#idm532065336464)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff](#idm532025426128) \[[GET](#idm532025423488)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff/{path:.\*}](#idm532027211472) \[[GET](#idm532025422208)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/watch](#idm532025446832) \[[POST](#idm532025445344), [DELETE](#idm532063383360)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare](#idm532025395568)
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes](#idm532025366384) \[[GET](#idm532025367952)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits](#idm532025378224) \[[GET](#idm532025377232)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/diff{path:.\*}](#idm532025393744) \[[GET](#idm532025392560)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff](#idm532061671952) \[[GET](#idm532061670480)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff/{path:.\*}](#idm532061652656) \[[GET](#idm532061651328)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files](#idm532026552512) \[[GET](#idm532026552256)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files/{path:.\*}](#idm532026540192) \[[GET](#idm532026536976)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified](#idm532026375296) \[[GET](#idm532026373776)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified/{path:.\*}](#idm532026362224) \[[GET](#idm532026360144)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants](#idm532025440688) \[[GET](#idm532025440064)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions](#idm532063342624)
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups](#idm532063341600) \[[GET](#idm532063341344), [PUT](#idm532064564656), [DELETE](#idm532064549280)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups/none](#idm532064540000) \[[GET](#idm532064538528)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users](#idm532064529856) \[[GET](#idm532064528016), [PUT](#idm532064518176), [DELETE](#idm532064504416)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users/none](#idm532064494400) \[[GET](#idm532064492928)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests](#idm532061891456) \[[POST](#idm532061892512), [GET](#idm532061876064)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}](#idm532061857808) \[[GET](#idm532061855088), [PUT](#idm532061854112), [DELETE](#idm532061832352)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/activities](#idm532061786272) \[[GET](#idm532061783952)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/decline](#idm532061798880) \[[POST](#idm532061796368)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge](#idm532061823200) \[[POST](#idm532061821248), [GET](#idm532061809648)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/reopen](#idm532061770544) \[[POST](#idm532061768496)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/approve](#idm532025588176) \[[POST](#idm532025586624), [DELETE](#idm532025575328)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/changes](#idm532026613024) \[[GET](#idm532064704784)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments](#idm532026059760) \[[GET](#idm532026059312), [POST](#idm532026042848)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}](#idm532026031408) \[[GET](#idm532026028800), [DELETE](#idm532026019568), [PUT](#idm532026009472)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/commits](#idm532026197296) \[[GET](#idm532026196144)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff](#idm532026613424) \[[GET](#idm532026596192)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff/{path:.\*}](#idm532026575552) \[[GET](#idm532026572640)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants](#idm532061633216) \[[GET](#idm532061631888), [POST](#idm532061623920), [DELETE](#idm532023725632)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug}](#idm532023715744) \[[DELETE](#idm532023712864), [PUT](#idm532023710608)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks](#idm532026179296) \[[GET](#idm532026178704)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks/count](#idm532026170752) \[[GET](#idm532026171504)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/watch](#idm532026246416) \[[POST](#idm532026245824), [DELETE](#idm532026239952)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw](#idm532027165280) \[[GET](#idm532027163792)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw/{path:.\*}](#idm532024748720) \[[GET](#idm532024747920)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings](#idm532025537536)
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/pull-requests](#idm532025538608) \[[POST](#idm532025537024), [GET](#idm532025525312)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks](#idm532023749840) \[[GET](#idm532023749344)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}](#idm532061908496) \[[GET](#idm532061906896), [DELETE](#idm532061899904)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/enabled](#idm532061929904) \[[PUT](#idm532061928944), [DELETE](#idm532061916048)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/settings](#idm532023739856) \[[GET](#idm532023738048), [PUT](#idm532023730240)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags](#idm532023645760) \[[GET](#idm532023644240), [POST](#idm532063377104)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags/{name:.\*}](#idm532063370592) \[[GET](#idm532063365616)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/watch](#idm532026260384) \[[POST](#idm532026259184), [DELETE](#idm532026252912)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks](#idm532063490592) \[[POST](#idm532063481456), [GET](#idm532063470320)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/test](#idm532026458112) \[[POST](#idm532026456640)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}](#idm532063458736) \[[DELETE](#idm532063456720), [GET](#idm532063451424), [PUT](#idm532026501696)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/latest](#idm532026493680) \[[GET](#idm532026490672)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics](#idm532026480752) \[[GET](#idm532026477744)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics/summary](#idm532026468928) \[[GET](#idm532026465920)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/settings](#idm532027304992)
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/pull-requests/{scmId}](#idm532027303696) \[[POST](#idm532027302512), [GET](#idm532063430336)\]

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/hooks](#idm532023631920) \[[GET](#idm532023631520)\]
    -

    - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}](#idm532027174304) \[[GET](#idm532027172704)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/enabled](#idm532027196656) \[[PUT](#idm532027194784), [DELETE](#idm532027192720)\]

    - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/settings](#idm532023621120) \[[GET](#idm532023619520), [PUT](#idm532023618720)\]

     

  - [http://example.com/rest/api/1.0/repos](#idm532026162096) \[[GET](#idm532026161600)\]

     

  - [http://example.com/rest/api/1.0/tasks](#idm532061728560) \[[POST](#idm532061726752)\]
    -

    - [http://example.com/rest/api/1.0/tasks/{taskId}](#idm532061716704) \[[GET](#idm532061715168), [DELETE](#idm532061708640), [PUT](#idm532061700144)\]

     

  - [http://example.com/rest/api/1.0/users](#idm532026233456) \[[GET](#idm532026232256), [PUT](#idm532026224512)\]
    -

    - [http://example.com/rest/api/1.0/users/credentials](#idm532025501440) \[[PUT](#idm532025496368)\]

    - [http://example.com/rest/api/1.0/users/{userSlug}](#idm532026214112) \[[GET](#idm532026213616)\]

    - [http://example.com/rest/api/1.0/users/{userSlug}/avatar.png](#idm532026205984) \[[DELETE](#idm532026204992), [POST](#idm532025502816)\]

     

  - [http://example.com/rest/api/1.0/users/{userSlug}/settings](#idm532025550848) \[[GET](#idm532025549392), [POST](#idm532025548688)\]

## Supported Filters

Filters are provided in query parameters in a standard `name=value` fashion. The following filters are currently supported:

- {@code filter} - return only users, whose username, name or email address *contain* the {@code filter} value
- {@code group} - return only users who are members of the given group
- {@code permission} - the "root" of a permission filter, whose value must be a valid global, project, or repository permission. Additional filter parameters referring to this filter that specify the resource (project or repository) to apply the filter to must be prefixed with `permission.`. See the section "Permission Filters" below for more details.
- {@code permission.N} - the "root" of a single permission filter, similar to the {@code permission} parameter, where "N" is a natural number starting from 1. This allows clients to specify multiple permission filters, by providing consecutive filters as {@code permission.1}, {@code permission.2} etc. Note that the filters numbering has to start with 1 and be continuous for all filters to be processed. The total allowed number of permission filters is 50 and all filters exceeding that limit will be dropped. See the section "Permission Filters" below for more details on how the permission filters are processed.

## Permission Filters

The following three sub-sections list parameters supported for permission filters (where `[root]` is the root permission filter name, e.g. {@code permission}, {@code permission.1} etc.) depending on the permission resource. The system determines which filter to apply (Global, Project or Repository permission) based on the `[root]` permission value. E.g. {@code ADMIN} is a global permission, {@code PROJECT_ADMIN} is a project permission and {@code REPO_ADMIN} is a repository permission. Note that the parameters for a given resource will be looked up in the order as they are listed below, that is e.g. for a project resource, if both {@code projectId} and {@code projectKey} are provided, the system will use {@code projectId} for the lookup.

#### Global permissions

The permission value under `[root]` is the only required and recognized parameter, as global permissions do not apply to a specific resource.

Example valid filter: `permission=ADMIN`.

#### Project permissions

- `[root]`- specifies the project permission
- `[root].projectId` - specifies the project ID to lookup the project by
- `[root].projectKey` - specifies the project key to lookup the project by

Example valid filter: `permission.1=PROJECT_ADMIN&permission.1.projectKey=TEST_PROJECT`.

#### Repository permissions

- `[root]`- specifies the repository permission
- `[root].projectId` - specifies the repository ID to lookup the repository by
- `[root].projectKey` and `[root].repositorySlug`- specifies the project key and repository slug to lookup the repository by; both values *need to* be provided for this look up to be triggered

Example valid filter: `permission.2=REPO_ADMIN&permission.2.projectKey=TEST_PROJECT&permission.2.repositorySlug=test_repo`.

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"}],"start":0}

  A page of users.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The search request was invalid, which may happen for multiple reasons, among others:

  - permission filter for project/repository permission with no parameters specifying the project or repository to apply the filter to
  - invalid permission name
  - permission filter for a project/repository permission pointing to a non-existent project or repository

  The exact reason for the error and - in most cases - the request parameter name that had invalid value - will be provided in the error message.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Authentication failed or was not attempted.

#### PUT

Update the currently authenticated user's details. The update will always be applied to the currently authenticated user.

*Example request representations:*

-

  application/json

  ###### Example

      {"name":null,"displayName":"Jane Citizen","email":"jane@example.com"}

*Example response representations:*

-

  200 - application/json (detailedUser)

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"}

  The updated user.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Authentication failed or was not attempted.
