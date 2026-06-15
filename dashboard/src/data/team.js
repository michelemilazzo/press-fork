import { createDocumentResource, frappeRequest } from 'frappe-ui';
import { clear } from 'idb-keyval';

let team;

export function getTeam() {
	if (!team) {
		team = createDocumentResource({
			doctype: 'Team',
			name: getCurrentTeam(),
			whitelistedMethods: {
				getTeamMembers: 'get_team_members',
				inviteTeamMember: 'invite_team_member',
				removeTeamMember: 'remove_team_member',
			},
		});
	}
	return team;
}

function getCurrentTeam() {
	if (
		document.cookie.includes('user_id=Guest') ||
		!document.cookie.includes('user_id')
	) {
		return null;
	}

	const validTeams = (window.valid_teams || [])
		.map((team) => team?.name)
		.filter(Boolean);
	const fallbackTeam = window.default_team || validTeams[0] || null;
	const currentTeam = localStorage.getItem('current_team');

	if (currentTeam && validTeams.includes(currentTeam)) {
		return currentTeam;
	}

	if (fallbackTeam) {
		localStorage.setItem('current_team', fallbackTeam);
	} else {
		localStorage.removeItem('current_team');
	}

	return fallbackTeam;
}

export async function switchToTeam(team) {
	let canSwitch = false;
	try {
		canSwitch = await frappeRequest({
			url: '/api/method/press.api.account.can_switch_to_team',
			params: { team },
		});
	} catch (error) {
		console.log(error);
		canSwitch = false;
	}
	if (canSwitch) {
		localStorage.setItem('current_team', team);

		// clear all cache from previous team session
		clear();

		window.location.reload();
	}
}

export async function isLastSite(team) {
	let count = 0;
	count = await frappeRequest({
		url: '/api/method/press.api.account.get_site_count',
		params: { team },
	});
	return Boolean(count === 1);
}

window.switchToTeam = switchToTeam;
