import time

from sqlalchemy import and_
from sqlalchemy.sql import func
from sqlalchemy import asc
from sqlalchemy.event import listen
from sqlalchemy.orm.attributes import NEVER_SET
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.attributes import get_history

from coprs import db
from coprs import exceptions
from coprs import helpers
from coprs import models
from coprs.exceptions import MalformedArgumentException
from coprs.logic import users_logic
from coprs.whoosheers import CoprWhoosheer

from coprs.logic.actions_logic import ActionsLogic
from coprs.logic.users_logic import UsersLogic


class CoprsLogic(object):
    """
    Used for manipulating Coprs.

    All methods accept user object as a first argument,
    as this may be needed in future.
    """

    @classmethod
    def get_all(cls):
        """ Return all coprs without those which are deleted. """
        query = (db.session.query(models.Copr)
                 .join(models.Copr.user)
                 .options(db.contains_eager(models.Copr.user))
                 .filter(models.Copr.deleted == False))
        return query

    @classmethod
    def get_by_id(cls, copr_id):
        return cls.get_all().filter(models.Copr.id == copr_id)

    @classmethod
    def attach_build(cls, query):
        query = (query.outerjoin(models.Copr.builds)
                 .options(db.contains_eager(models.Copr.builds))
                 .order_by(models.Build.submitted_on.desc()))
        return query

    @classmethod
    def attach_mock_chroots(cls, query):
        query = (query.outerjoin(*models.Copr.mock_chroots.attr)
                 .options(db.contains_eager(*models.Copr.mock_chroots.attr))
                 .order_by(models.MockChroot.os_release.asc())
                 .order_by(models.MockChroot.os_version.asc())
                 .order_by(models.MockChroot.arch.asc()))
        return query

    @classmethod
    def get(cls, username, coprname, **kwargs):
        with_builds = kwargs.get("with_builds", False)
        with_mock_chroots = kwargs.get("with_mock_chroots", False)

        query = (
            cls.get_all()
            .filter(models.Copr.name == coprname)
            .filter(models.User.username == username)
        )

        if with_builds:
            query = cls.attach_build(query)

        if with_mock_chroots:
            query = cls.attach_mock_chroots(query)

        return query

    @classmethod
    def get_multiple_by_group_id(cls, group_id, **kwargs):
        with_builds = kwargs.get("with_builds", False)
        with_mock_chroots = kwargs.get("with_mock_chroots", False)

        query = (
            cls.get_all()
            .filter(models.Copr.group_id == group_id)
        )

        if with_builds:
            query = cls.attach_build(query)

        if with_mock_chroots:
            query = cls.attach_mock_chroots(query)

        return query

    @classmethod
    def get_by_group_id(cls, group_id, coprname, **kwargs):
        query = cls.get_multiple_by_group_id(group_id, **kwargs)
        query = query.filter(models.Copr.name == coprname)

        return query

    @classmethod
    def get_multiple(cls, include_deleted=False, include_unlisted_on_hp=True):
        query = (
            db.session.query(models.Copr)
            .join(models.Copr.user)
            .outerjoin(models.Group)
            .options(db.contains_eager(models.Copr.user))
        )

        if not include_deleted:
            query = query.filter(models.Copr.deleted.is_(False))

        if not include_unlisted_on_hp:
            query = query.filter(models.Copr.unlisted_on_hp.is_(False))

        return query

    @classmethod
    def set_query_order(cls, query, desc=False):
        if desc:
            query = query.order_by(models.Copr.id.desc())
        else:
            query = query.order_by(models.Copr.id.asc())
        return query

    # user_relation="owned", username=username, with_mock_chroots=False
    @classmethod
    def get_multiple_owned_by_username(cls, username):
        query = cls.get_multiple()
        return query.filter(models.User.username == username)

    @classmethod
    def filter_by_name(cls, query, name):
        return query.filter(models.Copr.name == name)

    @classmethod
    def filter_by_user_name(cls, query, username):
        # should be already joined with the User table
        return query.filter(models.User.username == username)

    @classmethod
    def filter_by_group_name(cls, query, group_name):
        # should be already joined with the Group table
        return query.filter(models.Group.name == group_name)

    @classmethod
    def filter_without_group_projects(cls, query):
        return query.filter(models.Copr.group_id.is_(None))

    @classmethod
    def join_builds(cls, query):
        return (query.outerjoin(models.Copr.builds)
                .options(db.contains_eager(models.Copr.builds))
                .order_by(models.Build.submitted_on.desc()))

    @classmethod
    def join_mock_chroots(cls, query):
        return (query.outerjoin(*models.Copr.mock_chroots.attr)
                .options(db.contains_eager(*models.Copr.mock_chroots.attr))
                .order_by(models.MockChroot.os_release.asc())
                .order_by(models.MockChroot.os_version.asc())
                .order_by(models.MockChroot.arch.asc()))

    @classmethod
    def get_playground(cls):
        return cls.get_all().filter(models.Copr.playground == True)

    @classmethod
    def set_playground(cls, user, copr):
        if user.admin:
            db.session.add(copr)
            pass
        else:
            raise exceptions.InsufficientRightsException(
                "User is not a system admin")

    @classmethod
    def get_multiple_fulltext(cls, search_string):
        query = (models.Copr.query.join(models.User)
                 .filter(models.Copr.deleted == False))
        if "/" in search_string: # copr search by its full name
            if search_string[0] == '@': # searching for @group/project
                group_name = "%{}%".format(search_string.split("/")[0][1:])
                project = "%{}%".format(search_string.split("/")[1])
                query = query.filter(and_(models.Group.name.ilike(group_name),
                                          models.Copr.name.ilike(project),
                                          models.Group.id == models.Copr.group_id))
                query = query.order_by(asc(func.length(models.Group.name)+func.length(models.Copr.name)))
            else: # searching for user/project
                user_name = "%{}%".format(search_string.split("/")[0])
                project = "%{}%".format(search_string.split("/")[1])
                query = query.filter(and_(models.User.username.ilike(user_name),
                                          models.Copr.name.ilike(project),
                                          models.User.id == models.Copr.user_id))
                query = query.order_by(asc(func.length(models.User.username)+func.length(models.Copr.name)))
        else: # fulltext search
            query = query.whooshee_search(search_string, whoosheer=CoprWhoosheer)
        return query

    @classmethod
    def add(cls, user, name, selected_chroots, repos=None, description=None,
            instructions=None, check_for_duplicates=False, group=None, persistent=False,
            auto_prune=True, **kwargs):

        if not user.admin and persistent:
            raise exceptions.NonAdminCannotCreatePersistentProject()

        if not user.admin and not auto_prune:
            raise exceptions.NonAdminCannotDisableAutoPrunning()

        copr = models.Copr(name=name,
                           repos=repos or u"",
                           user_id=user.id,
                           description=description or u"",
                           instructions=instructions or u"",
                           created_on=int(time.time()),
                           persistent=persistent,
                           auto_prune=auto_prune,
                           **kwargs)

        if group is not None:
            UsersLogic.raise_if_not_in_group(user, group)
            copr.group = group

        # form validation checks for duplicates
        cls.new(user, copr, check_for_duplicates=check_for_duplicates)
        CoprChrootsLogic.new_from_names(copr, selected_chroots)

        db.session.flush()
        ActionsLogic.send_create_gpg_key(copr)

        return copr

    @classmethod
    def new(cls, user, copr, check_for_duplicates=True):
        if check_for_duplicates:
            if copr.group is None and cls.exists_for_user(user, copr.name).all():
                raise exceptions.DuplicateException(
                    "Copr: '{0}/{1}' already exists".format(user.name, copr.name))
            elif copr.group:
                db.session.flush()  # otherwise copr.id is not set from sequence
                if cls.exists_for_group(copr.group, copr.name).filter(models.Copr.id != copr.id).all():
                    db.session.rollback()
                    raise exceptions.DuplicateException(
                        "Copr: '@{0}/{1}' already exists".format(copr.group.name, copr.name))
        db.session.add(copr)

    @classmethod
    def update(cls, user, copr):
        # we should call get_history before other requests, otherwise
        # the changes would be forgotten
        if get_history(copr, "name").has_changes():
            raise MalformedArgumentException("Change name of the project is forbidden")

        users_logic.UsersLogic.raise_if_cant_update_copr(
            user, copr, "Only owners and admins may update their projects.")

        if not user.admin and not copr.auto_prune:
            raise exceptions.NonAdminCannotDisableAutoPrunning()

        db.session.add(copr)

    @classmethod
    def delete_unsafe(cls, user, copr):
        """
        Deletes copr without termination of ongoing builds.
        """
        cls.raise_if_cant_delete(user, copr)
        # TODO: do we want to dump the information somewhere, so that we can
        # search it in future?
        cls.raise_if_unfinished_blocking_action(
            copr, "Can't delete this project,"
                  " another operation is in progress: {action}")

        cls.create_delete_action(copr)
        copr.deleted = True

        return copr

    @classmethod
    def create_delete_action(cls, copr):
        action = models.Action(action_type=helpers.ActionTypeEnum("delete"),
                               object_type="copr",
                               object_id=copr.id,
                               old_value=copr.full_name,
                               new_value="",
                               created_on=int(time.time()))
        db.session.add(action)
        return action

    @classmethod
    def exists_for_user(cls, user, coprname, incl_deleted=False):
        existing = (models.Copr.query
                    .filter(models.Copr.name == coprname)
                    .filter(models.Copr.user_id == user.id))

        if not incl_deleted:
            existing = existing.filter(models.Copr.deleted == False)

        return cls.filter_without_group_projects(existing)

    @classmethod
    def exists_for_group(cls, group, coprname, incl_deleted=False):
        existing = (models.Copr.query
                    .filter(models.Copr.name == coprname)
                    .filter(models.Copr.group_id == group.id))

        if not incl_deleted:
            existing = existing.filter(models.Copr.deleted == False)

        return existing

    @classmethod
    def unfinished_blocking_actions_for(cls, copr):
        blocking_actions = [helpers.ActionTypeEnum("rename"),
                            helpers.ActionTypeEnum("delete")]

        actions = (models.Action.query
                   .filter(models.Action.object_type == "copr")
                   .filter(models.Action.object_id == copr.id)
                   .filter(models.Action.result ==
                           helpers.BackendResultEnum("waiting"))
                   .filter(models.Action.action_type.in_(blocking_actions)))

        return actions

    @classmethod
    def raise_if_unfinished_blocking_action(cls, copr, message):
        """
        Raise ActionInProgressException if given copr has an unfinished
        action. Return None otherwise.
        """

        unfinished_actions = cls.unfinished_blocking_actions_for(copr).all()
        if unfinished_actions:
            raise exceptions.ActionInProgressException(
                message, unfinished_actions[0])

    @classmethod
    def raise_if_cant_delete(cls, user, copr):
        """
        Raise InsufficientRightsException if given copr cant be deleted
        by given user. Return None otherwise.
        """

        if not user.admin and user != copr.user:
            raise exceptions.InsufficientRightsException(
                "Only owners may delete their projects.")

    @classmethod
    def changeable(cls, copr, modularity_property):
        if not getattr(copr, modularity_property):
            return True
        return not copr.modules


class CoprPermissionsLogic(object):
    @classmethod
    def get(cls, copr, searched_user):
        query = (models.CoprPermission.query
                 .filter(models.CoprPermission.copr == copr)
                 .filter(models.CoprPermission.user == searched_user))

        return query

    @classmethod
    def get_for_copr(cls, copr):
        query = models.CoprPermission.query.filter(
            models.CoprPermission.copr == copr)

        return query

    @classmethod
    def new(cls, copr_permission):
        db.session.add(copr_permission)

    @classmethod
    def update_permissions(cls, user, copr, copr_permission,
                           new_builder, new_admin):

        users_logic.UsersLogic.raise_if_cant_update_copr(
            user, copr, "Only owners and admins may update"
                        " their projects permissions.")

        (models.CoprPermission.query
         .filter(models.CoprPermission.copr_id == copr.id)
         .filter(models.CoprPermission.user_id == copr_permission.user_id)
         .update({"copr_builder": new_builder,
                  "copr_admin": new_admin}))

    @classmethod
    def update_permissions_by_applier(cls, user, copr, copr_permission, new_builder, new_admin):
        if copr_permission:
            # preserve approved permissions if set
            if (not new_builder or
                    copr_permission.copr_builder != helpers.PermissionEnum("approved")):

                copr_permission.copr_builder = new_builder

            if (not new_admin or
                    copr_permission.copr_admin != helpers.PermissionEnum("approved")):

                copr_permission.copr_admin = new_admin
        else:
            perm = models.CoprPermission(
                user=user,
                copr=copr,
                copr_builder=new_builder,
                copr_admin=new_admin)

            cls.new(perm)

    @classmethod
    def delete(cls, copr_permission):
        db.session.delete(copr_permission)


def on_auto_createrepo_change(target_copr, value_acr, old_value_acr, initiator):
    """ Emit createrepo action when auto_createrepo re-enabled"""
    if old_value_acr == NEVER_SET:
        #  created new copr, not interesting
        return
    if not old_value_acr and value_acr:
        #  re-enabled
        ActionsLogic.send_createrepo(
            target_copr.owner_name,
            target_copr.name,
            chroots=[chroot.name for chroot in target_copr.active_chroots]
        )


listen(models.Copr.auto_createrepo, 'set', on_auto_createrepo_change,
       active_history=True, retval=False)


class CoprChrootsLogic(object):
    @classmethod
    def mock_chroots_from_names(cls, names):

        db_chroots = models.MockChroot.query.all()
        mock_chroots = []
        for ch in db_chroots:
            if ch.name in names:
                mock_chroots.append(ch)

        return mock_chroots

    @classmethod
    def get_by_name(cls, copr, chroot_name):
        mc = MockChrootsLogic.get_from_name(chroot_name, active_only=True).one()
        query = (
            models.CoprChroot.query.join(models.MockChroot)
            .filter(models.CoprChroot.copr_id == copr.id)
            .filter(models.MockChroot.id == mc.id)
        )
        return query

    @classmethod
    def get_by_name_safe(cls, copr, chroot_name):
        """
        :rtype: models.CoprChroot
        """
        try:
            return cls.get_by_name(copr, chroot_name).one()
        except NoResultFound:
            return None

    @classmethod
    def new(cls, mock_chroot):
        db.session.add(mock_chroot)

    @classmethod
    def new_from_names(cls, copr, names):
        for mock_chroot in cls.mock_chroots_from_names(names):
            db.session.add(
                models.CoprChroot(copr=copr, mock_chroot=mock_chroot))

    @classmethod
    def create_chroot(cls, user, copr, mock_chroot,
                      buildroot_pkgs=None, repos=None, comps=None, comps_name=None, module_md=None, module_md_name=None):
        """
        :type user: models.User
        :type mock_chroot: models.MockChroot
        """
        if buildroot_pkgs is None:
            buildroot_pkgs = ""
        if repos is None:
            repos = ""
        UsersLogic.raise_if_cant_update_copr(
            user, copr,
            "Only owners and admins may update their projects.")

        chroot = models.CoprChroot(copr=copr, mock_chroot=mock_chroot)
        cls._update_chroot(buildroot_pkgs, repos, comps, comps_name, module_md, module_md_name, chroot)
        return chroot

    @classmethod
    def update_chroot(cls, user, copr_chroot,
                      buildroot_pkgs=None, repos=None, comps=None, comps_name=None, module_md=None, module_md_name=None):
        """
        :type user: models.User
        :type copr_chroot: models.CoprChroot
        """
        UsersLogic.raise_if_cant_update_copr(
            user, copr_chroot.copr,
            "Only owners and admins may update their projects.")

        cls._update_chroot(buildroot_pkgs, repos, comps, comps_name, module_md, module_md_name, copr_chroot)
        return copr_chroot

    @classmethod
    def _update_chroot(cls, buildroot_pkgs, repos, comps, comps_name, module_md, module_md_name, copr_chroot):
        if buildroot_pkgs is not None:
            copr_chroot.buildroot_pkgs = buildroot_pkgs

        if repos is not None:
            copr_chroot.repos = repos.replace("\n", " ")

        if comps_name is not None:
            copr_chroot.update_comps(comps)
            copr_chroot.comps_name = comps_name
            ActionsLogic.send_update_comps(copr_chroot)

        if module_md_name is not None:
            copr_chroot.update_module_md(module_md)
            copr_chroot.module_md_name = module_md_name
            ActionsLogic.send_update_module_md(copr_chroot)

        db.session.add(copr_chroot)

    @classmethod
    def update_from_names(cls, user, copr, names):
        UsersLogic.raise_if_cant_update_copr(
            user, copr,
            "Only owners and admins may update their projects.")
        current_chroots = copr.mock_chroots
        new_chroots = cls.mock_chroots_from_names(names)
        # add non-existing
        for mock_chroot in new_chroots:
            if mock_chroot not in current_chroots:
                db.session.add(
                    models.CoprChroot(copr=copr, mock_chroot=mock_chroot))

        # delete no more present
        to_remove = []
        for mock_chroot in current_chroots:
            if mock_chroot not in new_chroots:
                # can't delete here, it would change current_chroots and break
                # iteration
                to_remove.append(mock_chroot)

        for mc in to_remove:
            copr.mock_chroots.remove(mc)

    @classmethod
    def remove_comps(cls, user, copr_chroot):
        UsersLogic.raise_if_cant_update_copr(
            user, copr_chroot.copr,
            "Only owners and admins may update their projects.")

        copr_chroot.comps_name = None
        copr_chroot.comps_zlib = None
        ActionsLogic.send_update_comps(copr_chroot)
        db.session.add(copr_chroot)

    @classmethod
    def remove_module_md(cls, user, copr_chroot):
        UsersLogic.raise_if_cant_update_copr(
            user, copr_chroot.copr,
            "Only owners and admins may update their projects.")

        copr_chroot.module_md_name = None
        copr_chroot.module_md_zlib = None
        ActionsLogic.send_update_module_md(copr_chroot)
        db.session.add(copr_chroot)

    @classmethod
    def remove_copr_chroot(cls, user, copr_chroot):
        """
        :param models.CoprChroot chroot:
        """
        UsersLogic.raise_if_cant_update_copr(
            user, copr_chroot.copr,
            "Only owners and admins may update their projects.")

        db.session.delete(copr_chroot)


class MockChrootsLogic(object):
    @classmethod
    def get(cls, os_release, os_version, arch, active_only=False, noarch=False):
        if noarch and not arch:
            return (models.MockChroot.query
                    .filter(models.MockChroot.os_release == os_release,
                            models.MockChroot.os_version == os_version))

        return (models.MockChroot.query
                .filter(models.MockChroot.os_release == os_release,
                        models.MockChroot.os_version == os_version,
                        models.MockChroot.arch == arch))

    @classmethod
    def get_from_name(cls, chroot_name, active_only=False, noarch=False):
        """
        chroot_name should be os-version-architecture, e.g. fedora-rawhide-x86_64
        the architecture could be optional with noarch=True

        Return MockChroot object for textual representation of chroot
        """

        name_tuple = cls.tuple_from_name(chroot_name, noarch=noarch)
        return cls.get(name_tuple[0], name_tuple[1], name_tuple[2],
                       active_only=active_only, noarch=noarch)

    @classmethod
    def get_multiple(cls, active_only=False):
        query = models.MockChroot.query
        if active_only:
            query = query.filter(models.MockChroot.is_active == True)
        return query

    @classmethod
    def add(cls, name):
        name_tuple = cls.tuple_from_name(name)
        if cls.get(*name_tuple).first():
            raise exceptions.DuplicateException(
                "Mock chroot with this name already exists.")
        new_chroot = models.MockChroot(os_release=name_tuple[0],
                                       os_version=name_tuple[1],
                                       arch=name_tuple[2])
        cls.new(new_chroot)
        return new_chroot

    @classmethod
    def new(cls, mock_chroot):
        db.session.add(mock_chroot)

    @classmethod
    def edit_by_name(cls, name, is_active):
        name_tuple = cls.tuple_from_name(name)
        mock_chroot = cls.get(*name_tuple).first()
        if not mock_chroot:
            raise exceptions.NotFoundException(
                "Mock chroot with this name doesn't exist.")

        mock_chroot.is_active = is_active
        cls.update(mock_chroot)
        return mock_chroot

    @classmethod
    def update(cls, mock_chroot):
        db.session.add(mock_chroot)

    @classmethod
    def delete_by_name(cls, name):
        name_tuple = cls.tuple_from_name(name)
        mock_chroot = cls.get(*name_tuple).first()
        if not mock_chroot:
            raise exceptions.NotFoundException(
                "Mock chroot with this name doesn't exist.")

        cls.delete(mock_chroot)

    @classmethod
    def delete(cls, mock_chroot):
        db.session.delete(mock_chroot)

    @classmethod
    def tuple_from_name(cls, name, noarch=False):
        """
        input should be os-version-architecture, e.g. fedora-rawhide-x86_64

        the architecture could be optional with noarch=True

        returns ("os", "version", "arch") or ("os", "version", None)
        """
        split_name = name.split("-")
        valid = False
        if noarch and len(split_name) in [2, 3]:
            valid = True
        if not noarch and len(split_name) == 3:
            valid = True

        if not valid:
            raise MalformedArgumentException(
                "Chroot name is not valid")

        if noarch and len(split_name) == 2:
            split_name.append(None)

        return tuple(split_name)
