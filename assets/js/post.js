"use strict";

function requestPollResults(poll_element, pollId) {
    return new Promise(function (resolve, reject) {
        let post = poll_element.closest(".post");
        const blogName = post.getElementsByClassName("blog-name")[0].innerHTML;
        const postId = post.dataset.postId;

        let poll_results_url;

        if (poll_element.classList.contains("expired-poll")) {
            poll_results_url = `/api/v1/poll/${blogName}/${postId}/${pollId}/results?expired=1`;
        } else {
            poll_results_url = `/api/v1/poll/${blogName}/${postId}/${pollId}/results`;
        }

        const pollResultsFetch = fetch(poll_results_url);

        pollResultsFetch.then((results) => {
            return results.json();
        }).then((parsed_results) => {
            return resolve(parsed_results);
        });
    })
}

function fill_poll_results(poll_element, results) {
    const sorted_poll_results = Object.entries(results.results).sort((a,b) => (a[1]-b[1])).reverse();

    // First we must find the total number of votes and the winner(s) of the poll
    let total_votes = 0;

    // Answer ID to winner status and amount of votes
    const processed_poll_results = {};
    const winner_vote_count = sorted_poll_results[0][1];

    for (let [answer_id, votes] of sorted_poll_results) {
        processed_poll_results[answer_id] = {"is_winner": (winner_vote_count == votes), "votes": votes};
        total_votes += votes
    }
    
    const answerIdChoiceElementArray = [];
    const pollChoices = poll_element.getElementsByClassName("poll-choices")[0];

    for (let choiceElement of pollChoices.children) {
        answerIdChoiceElementArray.push([choiceElement.dataset.answerId, choiceElement]);
    }

    for (let [answer_id, choiceElement] of answerIdChoiceElementArray) {
        const answer_results = processed_poll_results[answer_id] || {"is_winner": false, "votes": 0};
        const is_winner = answer_results.is_winner;
        const answer_votes = answer_results.votes;

        let numericalVoteProportion

        if (answer_votes == 0 || total_votes == 0) {
            numericalVoteProportion = 0;
        } else {
            numericalVoteProportion = answer_votes/total_votes;
        }

        const voteProportionElement = document.createElement("span");
        voteProportionElement.classList.add("vote-proportion");
        voteProportionElement["style"] = `width: ${((numericalVoteProportion) * 100).toFixed(3)}%;`;

        const voteCountElement = document.createElement("p");
        voteCountElement.classList.add("vote-count");

        // A greater rounding precision is needed here
        const comparison = Math.round((numericalVoteProportion) * 10000)/10000
        if ((comparison > 0.001) || comparison == 0) {
            voteCountElement.innerHTML = new Intl.NumberFormat("en-US", {style: "percent", maximumSignificantDigits: 3}).format(Math.round((numericalVoteProportion) * 1000)/1000);
        } else {
            voteCountElement.innerHTML = "< 0.1%";
        }

        if (is_winner) {
            choiceElement.classList.add("poll-winner");
        }

        choiceElement.appendChild(voteProportionElement);
        choiceElement.appendChild(voteCountElement);
    }

    const pollMetadataElement = poll_element.getElementsByClassName("poll-metadata")[0]

    const totalVotesElement = document.createElement("span")
    totalVotesElement.innerHTML = `${total_votes} votes`

    const separatorElement = document.createElement("span")
    separatorElement.innerHTML = '•'
    separatorElement.classList.add("separator")

    const pollTimestamp = pollMetadataElement.children[0]

    const newMetadataContents = document.createDocumentFragment()
    newMetadataContents.append(totalVotesElement, separatorElement, pollTimestamp.cloneNode(true))

    pollTimestamp.replaceWith(newMetadataContents)

    poll_element.classList.add("populated")
}

const pollBlocks = document.getElementsByClassName("poll-block");


function populate_polls() {
    for (let poll of pollBlocks) {
        if (poll.classList.contains("populated")) {
            continue;
        }

        requestPollResults(poll, poll.dataset.pollId).then((answers) => {fill_poll_results(poll, answers)})
    }    
};

// TODO lazy load polls
populate_polls();

const unblurCommunityLabledPostButtons = document.getElementsByClassName("unblur-post-button");
for (let btn of unblurCommunityLabledPostButtons) {
    btn.addEventListener('click', function(event) {
        let postContentElement = btn.closest(".post-content");
        let communityTagCoverElement = postContentElement.getElementsByClassName("community-label-cover")

        communityTagCoverElement[0]["style"] = `display: none;`;
        postContentElement["style"] = `height: unset;`;
    })
}