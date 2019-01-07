from flask_script import Command, Option
from coprs import db
from coprs.logic import coprs_logic, actions_logic


class DeleteOutdatedChrootsCommand(Command):
    """
    Delete data in all chroots that are considered as outdated. That means, the chroot is EOL
    and the preservation period is over because admin of the project didn't extend its duration.
    """
    option_list = [
        Option("--dry-run", action="store_true",
               help="Do not actually remove any data, but rather print information on stdout"),
    ]

    def run(self, dry_run):
        self.dry_run = dry_run

        chroots = coprs_logic.CoprChrootsLogic \
            .filter_outdated_to_be_deleted(coprs_logic.CoprChrootsLogic.get_multiple())
        for i, chroot in enumerate(chroots, start=1):
            # This command will possibly delete a lot of chroots and can be a performance issue when committing
            # all at once. We are going to commit every x actions to avoid that.
            if i % 1000 == 0 and not self.dry_run:
                db.session.commit()
            self.delete(chroot)
        db.session.commit()

    def delete(self, chroot):
        if self.dry_run:
            print("Add delete_chroot action for {} in {}".format(chroot.name, chroot.copr.full_name))
        else:
            actions_logic.ActionsLogic.send_delete_chroot(chroot)
